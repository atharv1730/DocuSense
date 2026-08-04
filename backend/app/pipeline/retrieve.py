"""
Stage 1 retrieval: embed the query and run pgvector cosine similarity
search over chunks, scoped to a workspace (and optionally a single
document + chunking strategy).
"""

import asyncio
import time
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings

genai.configure(api_key=settings.GOOGLE_API_KEY)


async def embed_query(query: str) -> list[float]:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: genai.embed_content(
            model=settings.EMBEDDING_MODEL,
            content=query,
            task_type="retrieval_query",
            output_dimensionality=settings.EMBEDDING_DIMS,
        ),
    )
    return result["embedding"]


async def retrieve_chunks(
    query: str,
    db: AsyncSession,
    workspace_id: str,
    document_id: str | None = None,
    chunking_strategy: str = "fixed",
    k: int | None = None,
) -> tuple[list[dict], int, list[str]]:
    """Returns (chunks, latency_ms_stage1, stage1_chunk_ids)."""
    k = k or settings.RETRIEVE_K
    start = time.perf_counter()

    query_embedding = await embed_query(query)

    sql = """
        SELECT
            c.id, c.text, c.page_number, c.chunk_index,
            c.char_start, c.char_end, c.chunking_strategy,
            d.filename
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.workspace_id = :workspace_id
          AND c.chunking_strategy = :chunking_strategy
    """
    params: dict = {
        "workspace_id": workspace_id,
        "chunking_strategy": chunking_strategy,
        "query_embedding": str(query_embedding),
        "k": k,
    }
    if document_id:
        sql += " AND c.document_id = :document_id"
        params["document_id"] = document_id

    sql += " ORDER BY c.embedding <=> :query_embedding LIMIT :k"

    result = await db.execute(text(sql), params)
    rows = [dict(r) for r in result.mappings().all()]

    latency_ms_stage1 = int((time.perf_counter() - start) * 1000)
    stage1_chunk_ids = [str(r["id"]) for r in rows]

    return rows, latency_ms_stage1, stage1_chunk_ids
