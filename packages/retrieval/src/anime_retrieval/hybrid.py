"""Hybrid retriever: dense (pgvector cosine) + sparse (Postgres FTS) → RRF fusion.

Reciprocal Rank Fusion (RRF) is a robust default for combining ranked
lists. It avoids the need to normalize across heterogeneous score scales (cosine
similarity vs ts_rank_cd) by ranking the inputs and summing reciprocal ranks:

    score(d) = Σ_r 1 / (k_rrf + rank_r(d))

where r runs over each ranked list and k_rrf is a smoothing constant (60 is
standard from Cormack et al. 2009).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anime_core.embedder import Embedder
from anime_core.resilience import AsyncCircuitBreaker, RetrievalUnavailableError, guarded
from anime_core.vector_index import VectorIndex, VectorMatch

from anime_retrieval.sparse import BM25Index, BM25Match
from anime_retrieval.types import Candidate

logger = logging.getLogger(__name__)


@dataclass
class _Accumulator:
    """Per-key state during RRF fusion."""

    text: str
    rrf: float = 0.0
    dense_score: float | None = None
    sparse_score: float | None = None


def reciprocal_rank_fusion(
    dense: list[VectorMatch],
    sparse: list[BM25Match],
    *,
    k_rrf: int = 60,
    top_k: int = 20,
) -> list[Candidate]:
    """Fuse two ranked lists via RRF. Preserves per-leg scores for observability."""
    acc: dict[tuple[int, int], _Accumulator] = {}

    for dense_rank, dense_hit in enumerate(dense):
        key = (dense_hit.mal_id, dense_hit.chunk_index)
        entry = acc.setdefault(key, _Accumulator(text=dense_hit.text))
        entry.rrf += 1.0 / (k_rrf + dense_rank + 1)
        entry.dense_score = dense_hit.score

    for sparse_rank, sparse_hit in enumerate(sparse):
        key = (sparse_hit.mal_id, sparse_hit.chunk_index)
        entry = acc.setdefault(key, _Accumulator(text=sparse_hit.text))
        entry.rrf += 1.0 / (k_rrf + sparse_rank + 1)
        entry.sparse_score = sparse_hit.score

    fused = [
        Candidate(
            mal_id=key[0],
            chunk_index=key[1],
            text=entry.text,
            dense_score=entry.dense_score,
            sparse_score=entry.sparse_score,
            hybrid_score=entry.rrf,
        )
        for key, entry in acc.items()
    ]
    fused.sort(key=lambda c: c.hybrid_score or 0.0, reverse=True)
    return fused[:top_k]


class HybridRetriever:
    """Orchestrates dense + sparse retrieval and RRF fusion."""

    def __init__(
        self,
        *,
        vector_index: VectorIndex,
        bm25_index: BM25Index,
        embedder: Embedder,
        rrf_k: int = 60,
        timeout_seconds: float = 2.0,
        on_leg_failure: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._vector = vector_index
        self._bm25 = bm25_index
        self._embedder = embedder
        self._rrf_k = rrf_k
        self._timeout = timeout_seconds
        # Both legs run on the caller's DB session. A leg cancelled by its timeout
        # mid-query leaves that session's transaction invalid, and every later
        # statement on it (the other leg, then the route's history write) raises
        # PendingRollbackError. The pipeline passes session.rollback here so a failed
        # leg degrades the request instead of turning it into a 500.
        self._on_leg_failure = on_leg_failure
        # One breaker per retrieval leg so a flapping pgvector doesn't keep being
        # hammered — it fast-fails and we run sparse-only until it recovers.
        self._dense_breaker = AsyncCircuitBreaker(name="pgvector")
        self._sparse_breaker = AsyncCircuitBreaker(name="bm25_fts")

    async def _recover_after_failed_leg(self) -> None:
        """Run the caller's recovery hook. A failing hook must not mask the fallback."""
        if self._on_leg_failure is None:
            return
        try:
            await self._on_leg_failure()
        except Exception:
            logger.warning("session recovery after a failed retrieval leg failed", exc_info=True)

    async def retrieve(
        self,
        query: str,
        *,
        k: int = 20,
        query_embedding: list[float] | None = None,
        tenant_id: str | None = None,
    ) -> list[Candidate]:
        """Return up to `k` fused candidates ranked by RRF score (desc).

        Resilient: dense and sparse each run behind a breaker+timeout. If one
        leg fails we fuse with the other; if BOTH fail we raise
        RetrievalUnavailableError so the service can degrade to the popular fallback.

        `query_embedding` is accepted as an override so the pipeline can compute
        it once and pass it through (avoiding a redundant OpenAI call).
        """
        if query_embedding is None:
            query_embedding = (await self._embedder.embed([query])).embeddings[0]

        dense_hits: list[VectorMatch] = []
        sparse_hits: list[BM25Match] = []
        dense_ok = sparse_ok = False

        try:
            dense_hits = await guarded(
                lambda: self._vector.search(query_embedding, k=k, tenant_id=tenant_id),
                breaker=self._dense_breaker,
                timeout_seconds=self._timeout,
            )
            dense_ok = True
        except Exception:
            logger.warning("dense (pgvector) retrieval failed; falling back to sparse-only")
            await self._recover_after_failed_leg()

        try:
            sparse_hits = await guarded(
                lambda: self._bm25.search(query, k=k, tenant_id=tenant_id),
                breaker=self._sparse_breaker,
                timeout_seconds=self._timeout,
            )
            sparse_ok = True
        except Exception:
            logger.warning("sparse (FTS) retrieval failed")
            await self._recover_after_failed_leg()

        if not dense_ok and not sparse_ok:
            raise RetrievalUnavailableError("both dense and sparse retrieval failed")

        return reciprocal_rank_fusion(
            dense_hits,
            sparse_hits,
            k_rrf=self._rrf_k,
            top_k=k,
        )
