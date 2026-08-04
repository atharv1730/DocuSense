"""
Stage 2 re-ranking using a local cross-encoder.

Phase 3 shipped rerank_chunks(enabled=False) as a pass-through. This fills
in the real cross-encoder scoring for enabled=True without changing the
function's signature or how the router calls it.
"""

import asyncio
import time
from app.config import settings


class CrossEncoderReranker:
    """Loads the cross-encoder model lazily on first use so it never
    blocks server startup (and the ~85MB download only happens once,
    on the first re-ranked request)."""

    def __init__(self):
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(settings.CROSS_ENCODER_MODEL)
        return self._model

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return list(self._get_model().predict(pairs))


_reranker: CrossEncoderReranker | None = None


def _get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker


async def rerank_chunks(
    query: str,
    chunks: list[dict],
    n: int,
    enabled: bool = False,
) -> tuple[list[dict], float | None, list[str] | None]:
    """Returns (reranked_chunks, latency_ms_stage2, stage2_chunk_ids)."""
    if not enabled:
        return chunks[:n], None, None

    start = time.perf_counter()
    loop = asyncio.get_event_loop()

    def _score() -> list[float]:
        reranker = _get_reranker()
        pairs = [(query, chunk["text"]) for chunk in chunks]
        return reranker.predict(pairs)

    # CrossEncoder.predict() is synchronous/CPU-bound; keep it off the
    # event loop.
    scores = await loop.run_in_executor(None, _score)

    scored = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    reranked = [chunk for chunk, _ in scored[:n]]

    latency_ms = (time.perf_counter() - start) * 1000
    stage2_chunk_ids = [str(chunk["id"]) for chunk in reranked]

    return reranked, latency_ms, stage2_chunk_ids
