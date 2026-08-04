"""Writes one row per chat query to retrieval_logs for eval baselines."""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def write_retrieval_log(
    db: AsyncSession,
    workspace_id: str,
    conversation_id: str | None,
    query: str,
    chunking_strategy: str,
    rerank_enabled: bool,
    stage1_chunk_ids: list[str],
    stage2_chunk_ids: list[str] | None,
    final_chunk_ids: list[str],
    answer: str,
    abstained: bool,
    latency_ms_stage1: int,
    latency_ms_stage2: float | None,
    latency_ms_generate: int,
    model: str,
) -> str:
    log_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO retrieval_logs (
                id, workspace_id, conversation_id, query, chunking_strategy,
                rerank_enabled, stage1_chunk_ids, stage2_chunk_ids, final_chunk_ids,
                answer, abstained, latency_ms_stage1, latency_ms_stage2,
                latency_ms_generate, model
            ) VALUES (
                :id, :workspace_id, :conversation_id, :query, :chunking_strategy,
                :rerank_enabled, CAST(:stage1_chunk_ids AS uuid[]), CAST(:stage2_chunk_ids AS uuid[]),
                CAST(:final_chunk_ids AS uuid[]), :answer, :abstained, :latency_ms_stage1,
                :latency_ms_stage2, :latency_ms_generate, :model
            )
        """),
        {
            "id": log_id,
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "query": query,
            "chunking_strategy": chunking_strategy,
            "rerank_enabled": rerank_enabled,
            "stage1_chunk_ids": stage1_chunk_ids,
            "stage2_chunk_ids": stage2_chunk_ids,
            "final_chunk_ids": final_chunk_ids,
            "answer": answer,
            "abstained": abstained,
            "latency_ms_stage1": latency_ms_stage1,
            "latency_ms_stage2": (
                int(latency_ms_stage2) if latency_ms_stage2 is not None else None
            ),
            "latency_ms_generate": latency_ms_generate,
            "model": model,
        },
    )
    await db.commit()
    return log_id
