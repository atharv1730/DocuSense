"""
Retrieval evaluation metrics computed over chunk_ratings + retrieval_logs.

Ground truth is user-supplied relevance ratings (1 = relevant, 0 = not
relevant) on the chunks that were actually shown to the user
(final_chunk_ids). Unrated chunks are ambiguous, so:

- precision@k only counts a query if ALL of its top-k final chunks are
  rated. Otherwise the query is excluded (not treated as 0).
- MRR only counts a query if at least one of its final chunks is rated
  relevant (rating=1). Queries with no rated-relevant chunk (whether
  unrated entirely, or rated but all irrelevant) are excluded.

Both exclusions mean precision@k and MRR are estimates over a subset of
traffic; `coverage()` reports what fraction of that traffic is actually
being measured so the numbers aren't read as more complete than they are.
"""

from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings

PRECISION_KS = (1, 3, 5)


@dataclass
class LogWithRatings:
    id: str
    chunking_strategy: str
    rerank_enabled: bool
    final_chunk_ids: list[str]
    ratings: dict[str, int] = field(default_factory=dict)


async def _load_logs(
    db: AsyncSession,
    workspace_id: str,
    chunking_strategy: str | None = None,
    rerank_enabled: bool | None = None,
    include_replays: bool = True,
) -> list[LogWithRatings]:
    sql = """
        SELECT id, chunking_strategy, rerank_enabled, final_chunk_ids
        FROM retrieval_logs
        WHERE workspace_id = :workspace_id
          AND final_chunk_ids IS NOT NULL
    """
    params: dict = {"workspace_id": workspace_id}
    if chunking_strategy is not None:
        sql += " AND chunking_strategy = :chunking_strategy"
        params["chunking_strategy"] = chunking_strategy
    if rerank_enabled is not None:
        sql += " AND rerank_enabled = :rerank_enabled"
        params["rerank_enabled"] = rerank_enabled
    if not include_replays:
        sql += " AND is_replay = false"

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    logs = {
        str(r["id"]): LogWithRatings(
            id=str(r["id"]),
            chunking_strategy=r["chunking_strategy"],
            rerank_enabled=r["rerank_enabled"],
            final_chunk_ids=[str(cid) for cid in (r["final_chunk_ids"] or [])],
        )
        for r in rows
    }
    if not logs:
        return []

    rating_result = await db.execute(
        text("""
            SELECT retrieval_log_id, chunk_id, rating
            FROM chunk_ratings
            WHERE retrieval_log_id = ANY(:log_ids)
        """),
        {"log_ids": list(logs.keys())},
    )
    for r in rating_result.mappings().all():
        log = logs.get(str(r["retrieval_log_id"]))
        if log is not None:
            log.ratings[str(r["chunk_id"])] = r["rating"]

    return list(logs.values())


def _precision_at_k(final_chunk_ids: list[str], ratings: dict[str, int], k: int) -> float | None:
    top_k = final_chunk_ids[:k]
    if len(top_k) < k:
        return None
    if not all(cid in ratings for cid in top_k):
        return None
    relevant = sum(1 for cid in top_k if ratings[cid] == 1)
    return relevant / k


def _mrr_for_log(final_chunk_ids: list[str], ratings: dict[str, int]) -> float | None:
    for rank, cid in enumerate(final_chunk_ids, start=1):
        if ratings.get(cid) == 1:
            return 1.0 / rank
    return None


async def precision_at_k(db: AsyncSession, log_id: str, k: int) -> float | None:
    """Precision@k for a single retrieval log. None if not all top-k
    chunks are rated."""
    result = await db.execute(
        text("SELECT final_chunk_ids FROM retrieval_logs WHERE id = :id"),
        {"id": log_id},
    )
    row = result.mappings().first()
    if row is None or not row["final_chunk_ids"]:
        return None
    final_chunk_ids = [str(cid) for cid in row["final_chunk_ids"]]

    rating_result = await db.execute(
        text("SELECT chunk_id, rating FROM chunk_ratings WHERE retrieval_log_id = :id"),
        {"id": log_id},
    )
    ratings = {str(r["chunk_id"]): r["rating"] for r in rating_result.mappings().all()}

    return _precision_at_k(final_chunk_ids, ratings, k)


async def mrr(db: AsyncSession, log_ids: list[str]) -> float | None:
    """Mean reciprocal rank over the given logs. None if no log has a
    rated-relevant chunk."""
    if not log_ids:
        return None
    result = await db.execute(
        text("SELECT id, final_chunk_ids FROM retrieval_logs WHERE id = ANY(:ids)"),
        {"ids": log_ids},
    )
    logs = {
        str(r["id"]): [str(cid) for cid in (r["final_chunk_ids"] or [])]
        for r in result.mappings().all()
    }

    rating_result = await db.execute(
        text("SELECT retrieval_log_id, chunk_id, rating FROM chunk_ratings WHERE retrieval_log_id = ANY(:ids)"),
        {"ids": log_ids},
    )
    ratings_by_log: dict[str, dict[str, int]] = {}
    for r in rating_result.mappings().all():
        ratings_by_log.setdefault(str(r["retrieval_log_id"]), {})[str(r["chunk_id"])] = r["rating"]

    reciprocal_ranks = []
    for log_id, final_chunk_ids in logs.items():
        rr = _mrr_for_log(final_chunk_ids, ratings_by_log.get(log_id, {}))
        if rr is not None:
            reciprocal_ranks.append(rr)

    if not reciprocal_ranks:
        return None
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


async def coverage(db: AsyncSession, workspace_id: str) -> float:
    """Fraction of retrieval_logs in the workspace that have all
    RERANK_N chunks rated."""
    logs = await _load_logs(db, workspace_id)
    if not logs:
        return 0.0
    fully_rated = sum(
        1
        for log in logs
        if len(log.final_chunk_ids) >= settings.RERANK_N
        and all(cid in log.ratings for cid in log.final_chunk_ids[: settings.RERANK_N])
    )
    return fully_rated / len(logs)


def _is_fully_rated(log: LogWithRatings) -> bool:
    return bool(log.final_chunk_ids) and all(cid in log.ratings for cid in log.final_chunk_ids)


async def per_config_metrics(db: AsyncSession, workspace_id: str) -> list[dict]:
    """Groups logs by (chunking_strategy, rerank_enabled) and computes
    precision@1/3/5, MRR, query count, and rated query count for each
    group."""
    logs = await _load_logs(db, workspace_id)

    groups: dict[tuple[str, bool], list[LogWithRatings]] = {}
    for log in logs:
        key = (log.chunking_strategy, log.rerank_enabled)
        groups.setdefault(key, []).append(log)

    results = []
    for (strategy, rerank_enabled), group_logs in groups.items():
        precisions: dict[int, list[float]] = {k: [] for k in PRECISION_KS}
        reciprocal_ranks = []
        rated_query_count = 0

        for log in group_logs:
            if log.ratings:
                rated_query_count += 1
            for k in PRECISION_KS:
                p = _precision_at_k(log.final_chunk_ids, log.ratings, k)
                if p is not None:
                    precisions[k].append(p)
            rr = _mrr_for_log(log.final_chunk_ids, log.ratings)
            if rr is not None:
                reciprocal_ranks.append(rr)

        fully_rated_count = sum(1 for log in group_logs if _is_fully_rated(log))

        results.append({
            "chunking_strategy": strategy,
            "rerank_enabled": rerank_enabled,
            "precision_at_1": sum(precisions[1]) / len(precisions[1]) if precisions[1] else None,
            "precision_at_3": sum(precisions[3]) / len(precisions[3]) if precisions[3] else None,
            "precision_at_5": sum(precisions[5]) / len(precisions[5]) if precisions[5] else None,
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None,
            "query_count": len(group_logs),
            "rated_query_count": rated_query_count,
            "coverage": fully_rated_count / len(group_logs) if group_logs else 0.0,
        })

    results.sort(key=lambda r: (r["chunking_strategy"], r["rerank_enabled"]))
    return results
