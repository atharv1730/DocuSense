import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db
from app.auth import get_current_user
from app.routers.documents import verify_workspace
from app.eval import metrics
from app.pipeline.retrieve import retrieve_chunks
from app.pipeline.rerank import rerank_chunks
from app.pipeline.log import write_retrieval_log
from app.config import settings
from app.schemas.eval import (
    SubmitRatingsRequest,
    MetricsResponse,
    ConfigMetrics,
    RetrievalLogsResponse,
    RetrievalLogOut,
    ChunkRatingOut,
    ChunkPreviewOut,
    ReplayRequest,
    ReplayResponse,
)
from typing import Optional

router = APIRouter(prefix="/workspaces/{workspace_id}/eval", tags=["eval"])


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    workspace_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)
    configs = await metrics.per_config_metrics(db, workspace_id)
    overall_coverage = await metrics.coverage(db, workspace_id)
    return MetricsResponse(
        configs=[ConfigMetrics(**c) for c in configs],
        overall_coverage=overall_coverage,
    )


@router.post("/ratings", status_code=204)
async def submit_ratings(
    workspace_id: str,
    body: SubmitRatingsRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    log_check = await db.execute(
        text("SELECT id FROM retrieval_logs WHERE id = :id AND workspace_id = :wid"),
        {"id": body.retrieval_log_id, "wid": workspace_id},
    )
    if not log_check.mappings().first():
        raise HTTPException(status_code=404, detail="Retrieval log not found")

    for rating in body.ratings:
        await db.execute(
            text("""
                INSERT INTO chunk_ratings (id, retrieval_log_id, chunk_id, rating)
                VALUES (:id, :log_id, :chunk_id, :rating)
                ON CONFLICT (retrieval_log_id, chunk_id)
                DO UPDATE SET rating = EXCLUDED.rating
            """),
            {
                "id": str(uuid.uuid4()),
                "log_id": body.retrieval_log_id,
                "chunk_id": rating.chunk_id,
                "rating": rating.rating,
            },
        )
    await db.commit()
    return Response(status_code=204)


@router.get("/logs", response_model=RetrievalLogsResponse)
async def list_logs(
    workspace_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    chunking_strategy: Optional[str] = None,
    rerank: Optional[bool] = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    where = ["workspace_id = :workspace_id"]
    params: dict = {"workspace_id": workspace_id}
    if chunking_strategy is not None:
        where.append("chunking_strategy = :chunking_strategy")
        params["chunking_strategy"] = chunking_strategy
    if rerank is not None:
        where.append("rerank_enabled = :rerank")
        params["rerank"] = rerank
    where_clause = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS n FROM retrieval_logs WHERE {where_clause}"),
        params,
    )
    total = count_result.mappings().first()["n"]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(
        text(f"""
            SELECT id, conversation_id, query, chunking_strategy, rerank_enabled,
                   is_replay, stage1_chunk_ids, stage2_chunk_ids, final_chunk_ids,
                   answer, abstained, created_at
            FROM retrieval_logs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = result.mappings().all()
    log_ids = [str(r["id"]) for r in rows]

    ratings_by_log: dict[str, list[ChunkRatingOut]] = {lid: [] for lid in log_ids}
    if log_ids:
        rating_result = await db.execute(
            text("SELECT retrieval_log_id, chunk_id, rating FROM chunk_ratings WHERE retrieval_log_id = ANY(:ids)"),
            {"ids": log_ids},
        )
        for r in rating_result.mappings().all():
            ratings_by_log[str(r["retrieval_log_id"])].append(
                ChunkRatingOut(chunk_id=str(r["chunk_id"]), rating=r["rating"])
            )

    logs = [
        RetrievalLogOut(
            id=str(r["id"]),
            conversation_id=str(r["conversation_id"]) if r["conversation_id"] else None,
            query=r["query"],
            chunking_strategy=r["chunking_strategy"],
            rerank_enabled=r["rerank_enabled"],
            is_replay=r["is_replay"],
            stage1_chunk_ids=[str(c) for c in r["stage1_chunk_ids"]] if r["stage1_chunk_ids"] else None,
            stage2_chunk_ids=[str(c) for c in r["stage2_chunk_ids"]] if r["stage2_chunk_ids"] else None,
            final_chunk_ids=[str(c) for c in r["final_chunk_ids"]] if r["final_chunk_ids"] else None,
            answer=r["answer"],
            abstained=r["abstained"],
            created_at=r["created_at"],
            ratings=ratings_by_log[str(r["id"])],
        )
        for r in rows
    ]

    all_chunk_ids: set[str] = set()
    for r in rows:
        for col in ("stage1_chunk_ids", "stage2_chunk_ids", "final_chunk_ids"):
            for cid in (r[col] or []):
                all_chunk_ids.add(str(cid))

    chunk_previews: dict[str, ChunkPreviewOut] = {}
    if all_chunk_ids:
        preview_result = await db.execute(
            text("""
                SELECT c.id, c.page_number, c.text, d.filename
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(:ids)
            """),
            {"ids": list(all_chunk_ids)},
        )
        for r in preview_result.mappings().all():
            chunk_previews[str(r["id"])] = ChunkPreviewOut(
                id=str(r["id"]),
                filename=r["filename"],
                page_number=r["page_number"],
                text=r["text"][:200],
            )

    return RetrievalLogsResponse(
        logs=logs, total=total, page=page, page_size=page_size, chunk_previews=chunk_previews
    )


@router.post("/replay", response_model=ReplayResponse)
async def replay(
    workspace_id: str,
    body: ReplayRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_workspace(workspace_id, user, db)

    result = await db.execute(
        text("SELECT id, query FROM retrieval_logs WHERE id = ANY(:ids) AND workspace_id = :wid"),
        {"ids": body.log_ids, "wid": workspace_id},
    )
    original_logs = {str(r["id"]): r["query"] for r in result.mappings().all()}
    missing = [lid for lid in body.log_ids if lid not in original_logs]
    if missing:
        raise HTTPException(status_code=404, detail=f"Retrieval logs not found: {missing}")

    new_log_ids = []
    for log_id in body.log_ids:
        query = original_logs[log_id]

        chunks, latency_ms_stage1, stage1_chunk_ids = await retrieve_chunks(
            query=query,
            db=db,
            workspace_id=workspace_id,
            document_id=None,
            chunking_strategy=body.chunking_strategy,
            k=settings.RETRIEVE_K,
        )

        if not chunks:
            reranked, latency_ms_stage2, stage2_chunk_ids = [], None, None
        else:
            reranked, latency_ms_stage2, stage2_chunk_ids = await rerank_chunks(
                query=query,
                chunks=chunks,
                n=settings.RERANK_N,
                enabled=body.rerank_enabled,
            )

        final_chunk_ids = [str(c["id"]) for c in reranked]

        new_log_id = await write_retrieval_log(
            db=db,
            workspace_id=workspace_id,
            conversation_id=None,
            query=query,
            chunking_strategy=body.chunking_strategy,
            rerank_enabled=body.rerank_enabled,
            stage1_chunk_ids=stage1_chunk_ids,
            stage2_chunk_ids=stage2_chunk_ids,
            final_chunk_ids=final_chunk_ids,
            answer=None,
            abstained=None,
            latency_ms_stage1=latency_ms_stage1,
            latency_ms_stage2=latency_ms_stage2,
            latency_ms_generate=None,
            model=None,
            is_replay=True,
        )
        new_log_ids.append(new_log_id)

    return ReplayResponse(log_ids=new_log_ids)
