import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.routers.documents import verify_workspace
from app.schemas.chat import ChatRequest
from app.pipeline.retrieve import retrieve_chunks
from app.pipeline.rerank import rerank_chunks
from app.pipeline.generate import generate_answer_stream
from app.pipeline.log import write_retrieval_log
from app.config import settings

router = APIRouter(prefix="/workspaces/{workspace_id}/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


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

    async def event_stream():
        # StreamingResponse iterates this generator after the request's
        # `db` dependency has already been torn down, so open a session
        # of our own for the lifetime of the stream.
        async with AsyncSessionLocal() as stream_db:
            try:
                chunks, latency_ms_stage1, stage1_chunk_ids = await retrieve_chunks(
                    query=body.query,
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
                    query=body.query,
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
                async for event in generate_answer_stream(body.query, reranked):
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
                    conversation_id=None,
                    query=body.query,
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
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to write retrieval log for workspace %s", workspace_id
                )

            yield _sse({
                "type": "done",
                "answer": full_answer,
                "citations": citations,
                "abstained": abstained,
                "retrieval_log_id": log_id,
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
