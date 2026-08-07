import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.routers.documents import verify_workspace
from app.schemas.chat import ChatRequest
from app.pipeline.retrieve import retrieve_chunks
from app.pipeline.rerank import rerank_chunks
from app.pipeline.generate import generate_answer_stream, rewrite_query
from app.pipeline.log import write_retrieval_log
from app.config import settings

router = APIRouter(prefix="/workspaces/{workspace_id}/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _fetch_history(db: AsyncSession, conversation_id: str) -> list[dict]:
    """Last CONVERSATION_HISTORY_TURNS messages for a conversation, oldest
    first, in the {"role", "content"} shape rewrite_query/generation expect.
    """
    result = await db.execute(
        text("""
            SELECT role, content FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"cid": conversation_id, "limit": settings.CONVERSATION_HISTORY_TURNS},
    )
    rows = list(reversed(result.mappings().all()))
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _save_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    retrieval_log_id: str | None = None,
) -> None:
    await db.execute(
        text("""
            INSERT INTO messages (id, conversation_id, role, content, citations, retrieval_log_id)
            VALUES (:id, :cid, :role, :content, CAST(:citations AS json), :retrieval_log_id)
        """),
        {
            "id": str(uuid.uuid4()),
            "cid": conversation_id,
            "role": role,
            "content": content,
            "citations": json.dumps(citations) if citations is not None else None,
            "retrieval_log_id": retrieval_log_id,
        },
    )


async def _touch_conversation(db: AsyncSession, conversation_id: str, first_message_title: str | None) -> None:
    if first_message_title:
        await db.execute(
            text("""
                UPDATE conversations
                SET updated_at = now(),
                    title = COALESCE(title, :title)
                WHERE id = :id
            """),
            {"id": conversation_id, "title": first_message_title[:80]},
        )
    else:
        await db.execute(
            text("UPDATE conversations SET updated_at = now() WHERE id = :id"),
            {"id": conversation_id},
        )


@router.post("")
async def chat(
    workspace_id: str,
    body: ChatRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verified up front with the request-scoped session, which is still
    # open at this point (unlike inside the generator below, which runs
    # after this endpoint function returns).
    await verify_workspace(workspace_id, user, db)

    if body.conversation_id:
        conv_check = await db.execute(
            text("SELECT id FROM conversations WHERE id = :id AND workspace_id = :wid"),
            {"id": body.conversation_id, "wid": workspace_id},
        )
        if not conv_check.mappings().first():
            raise HTTPException(status_code=404, detail="Conversation not found")

    async def event_stream():
        # StreamingResponse iterates this generator after the request's
        # `db` dependency has already been torn down, so open a session
        # of our own for the lifetime of the stream.
        async with AsyncSessionLocal() as stream_db:
            history: list[dict] = []
            if body.conversation_id:
                history = await _fetch_history(stream_db, body.conversation_id)

            # Retrieval benefits from an explicit standalone query;
            # generation benefits from the full conversational context. Only
            # pay for the rewrite call when there's actually history to
            # resolve against - the first message in a conversation is
            # always already standalone.
            standalone_query = body.query
            rewritten = False
            if history:
                try:
                    standalone_query = await rewrite_query(body.query, history)
                    rewritten = True
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Query rewrite failed for workspace %s; falling back to original query",
                        workspace_id,
                    )
                    standalone_query = body.query
                    rewritten = False

            try:
                chunks, latency_ms_stage1, stage1_chunk_ids = await retrieve_chunks(
                    query=standalone_query,
                    db=stream_db,
                    workspace_id=workspace_id,
                    document_id=body.document_id,
                    chunking_strategy=body.chunking_strategy,
                    k=settings.RETRIEVE_K,
                )
            except Exception as exc:
                yield _sse({"type": "error", "message": f"Retrieval failed: {exc}"})
                return

            if not chunks:
                yield _sse({
                    "type": "error",
                    "message": "No relevant content found. Upload and wait for a document to finish processing first.",
                })
                return

            try:
                reranked, latency_ms_stage2, stage2_chunk_ids = await rerank_chunks(
                    query=standalone_query,
                    chunks=chunks,
                    n=settings.RERANK_N,
                    enabled=body.rerank_enabled,
                )
            except NotImplementedError:
                reranked = chunks[: settings.RERANK_N]
                latency_ms_stage2, stage2_chunk_ids = None, None

            final_chunk_ids = [str(c["id"]) for c in reranked]

            full_answer = ""
            citations: list[dict] = []
            abstained = False
            latency_ms_generate = 0

            try:
                async for event in generate_answer_stream(body.query, reranked, history=history):
                    if event["type"] == "token":
                        yield _sse(event)
                    elif event["type"] == "done":
                        full_answer = event["answer"]
                        citations = event["citations"]
                        abstained = event["abstained"]
                        latency_ms_generate = event["latency_ms_generate"]
            except Exception as exc:
                yield _sse({"type": "error", "message": f"Generation failed: {exc}"})
                return

            # Logging happens after the answer has already reached the
            # client; never let a logging failure strand the stream
            # without a final event.
            log_id = None
            try:
                log_id = await write_retrieval_log(
                    db=stream_db,
                    workspace_id=workspace_id,
                    conversation_id=body.conversation_id,
                    query=standalone_query,
                    chunking_strategy=body.chunking_strategy,
                    rerank_enabled=body.rerank_enabled,
                    stage1_chunk_ids=stage1_chunk_ids,
                    stage2_chunk_ids=stage2_chunk_ids,
                    final_chunk_ids=final_chunk_ids,
                    answer=full_answer,
                    abstained=abstained,
                    latency_ms_stage1=latency_ms_stage1,
                    latency_ms_stage2=latency_ms_stage2,
                    latency_ms_generate=latency_ms_generate,
                    model=settings.GENERATION_MODEL,
                    rewritten=rewritten,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to write retrieval log for workspace %s", workspace_id
                )

            if body.conversation_id:
                try:
                    await _save_message(stream_db, body.conversation_id, "user", body.query)
                    await _save_message(
                        stream_db,
                        body.conversation_id,
                        "assistant",
                        full_answer,
                        citations=citations,
                        retrieval_log_id=log_id,
                    )
                    is_first_message = not history
                    await _touch_conversation(
                        stream_db,
                        body.conversation_id,
                        first_message_title=body.query if is_first_message else None,
                    )
                    await stream_db.commit()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Failed to persist messages for conversation %s", body.conversation_id
                    )

            # Full final-chunk list (not just cited ones) so the client can
            # render a rating card for every chunk shown to the generator.
            rated_chunks = [
                {
                    "id": str(c["id"]),
                    "filename": c["filename"],
                    "page_number": c["page_number"],
                    "text": c["text"][:300],
                }
                for c in reranked
            ]

            yield _sse({
                "type": "done",
                "answer": full_answer,
                "citations": citations,
                "abstained": abstained,
                "retrieval_log_id": log_id,
                "chunks": rated_chunks,
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
