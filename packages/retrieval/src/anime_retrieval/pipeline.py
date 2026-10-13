"""Top-level retrieval pipeline orchestrator.

Wires the full chain:

    query
      → embed
      → hybrid retrieve (dense pgvector + BM25 FTS → RRF fuse)
      → dedup by anime (one chunk per mal_id, keep highest hybrid_score)
      → cross-encoder rerank
      → MMR diversify (λ=0.85, configurable via MMR_LAMBDA)
      → top-3 final
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import time

from anime_core.db.models import AnimeChunk as ORMChunk
from anime_core.embedder import Embedder
from anime_core.observability.metrics import record_retrieval_stage
from anime_core.resilience import RetrievalUnavailableError
from anime_core.vector_index import PgvectorIndex
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from anime_retrieval.hybrid import HybridRetriever
from anime_retrieval.mmr import mmr_select
from anime_retrieval.reranker import BgeReranker, Reranker
from anime_retrieval.sparse import PostgresBM25Index
from anime_retrieval.types import Candidate

logger = logging.getLogger(__name__)

# Reranker timeout (seconds). The cross-encoder is CPU-bound; if it stalls we skip
# it rather than blow the latency budget.
DEFAULT_RERANK_TIMEOUT = float(os.environ.get("RERANK_TIMEOUT", "2.0"))

# MMR relevance/diversity trade-off. Raised 0.7 → 0.85 after eval measurement:
# λ=0.7 over-diversified, dropping relevant franchise entries from slots 2-3 and
# costing recall@3. Higher λ favors relevance. Overridable via MMR_LAMBDA env.
DEFAULT_MMR_LAMBDA = 0.85


def resolve_mmr_lambda(explicit: float | None = None) -> float:
    """Resolve MMR lambda: explicit arg > MMR_LAMBDA env var > DEFAULT_MMR_LAMBDA."""
    if explicit is not None:
        return explicit
    raw = os.environ.get("MMR_LAMBDA")
    return float(raw) if raw else DEFAULT_MMR_LAMBDA


def _dedup_by_anime(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the first (highest-scored, since input is sorted) chunk per mal_id."""
    seen: set[int] = set()
    out: list[Candidate] = []
    for c in candidates:
        if c.mal_id in seen:
            continue
        seen.add(c.mal_id)
        out.append(c)
    return out


async def _fetch_embeddings(
    session: AsyncSession,
    keys: list[tuple[int, int]],
) -> dict[tuple[int, int], list[float]]:
    """Fetch embeddings for a small set of (mal_id, chunk_index) keys in one round trip."""
    if not keys:
        return {}
    stmt = select(
        ORMChunk.mal_id,
        ORMChunk.chunk_index,
        ORMChunk.embedding,
    ).where(tuple_(ORMChunk.mal_id, ORMChunk.chunk_index).in_(keys))
    result = await session.execute(stmt)
    return {(int(row.mal_id), int(row.chunk_index)): list(row.embedding) for row in result}


class RetrievalPipeline:
    """Full retrieval pipeline."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        embedder: Embedder,
        reranker: Reranker | None = None,
        hybrid_k: int = 20,
        rerank_k: int = 5,
        final_k: int = 3,
        mmr_lambda: float | None = None,
        rerank_timeout: float = DEFAULT_RERANK_TIMEOUT,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._reranker: Reranker = reranker or BgeReranker()
        self._rerank_timeout = rerank_timeout
        self._hybrid = HybridRetriever(
            vector_index=PgvectorIndex(session),
            bm25_index=PostgresBM25Index(session),
            embedder=embedder,
            # Both legs share this session (and so does the route's history write);
            # a failed leg must roll it back before anything else runs on it.
            on_leg_failure=session.rollback,
        )
        self._hybrid_k = hybrid_k
        self._rerank_k = rerank_k
        self._final_k = final_k
        self._mmr_lambda = resolve_mmr_lambda(mmr_lambda)

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str | None = None,
    ) -> list[Candidate]:
        # 1) Embed the query once; reused for hybrid retrieval AND MMR relevance.
        #
        # GUARDED, and the guard is load-bearing. The embedder is a REMOTE call
        # (OpenAI text-embedding-3-small) behind a cache, so on a cache MISS an
        # embedding-provider outage raises right here — before hybrid retrieval, and
        # before the LLM degradation boundary in RecommendationService.recommend().
        # Unguarded, that escaped as HTTP 500 for EVERY request.
        #
        # Measured 2026-09-22 by `make chain-drill` step 4, which blackholes
        # api.openai.com — and so takes out the embedder as well as the OpenAI LLM
        # leg. The consequence was wildly out of proportion to the cause: a
        # third-party EMBEDDING outage 500'd the whole app while the self-hosted LLM
        # leg, the Groq leg and the local Postgres corpus were all healthy.
        #
        # Translating to RetrievalUnavailableError routes it into the degradation
        # path that already exists (service.py catches it → popular_fallback), so the
        # client gets 200 + degraded + real corpus titles instead of a stack trace.
        #
        # The cache is why this stayed hidden for so long: a repeated query never
        # reaches the provider, so only a cold cache key exposes it.
        #
        # NOT sparse-only degradation, deliberately. BM25 needs no embedding, so
        # falling back to sparse would serve better results than the popular floor —
        # but this embedding is also what MMR scores relevance against (step 5), so
        # skipping it means reworking diversification too. That is a real improvement
        # and a bigger change; it is tracked separately rather than smuggled into a
        # fix whose job is to stop returning 500s.
        started = time.perf_counter()
        try:
            query_embedding = (await self._embedder.embed([query])).embeddings[0]
        except Exception as exc:
            # Record the failed stage. Otherwise an embedder burning its full timeout
            # on every request looks FREE on the dashboard — the same reasoning the
            # dense and sparse legs already apply in HybridRetriever.retrieve().
            record_retrieval_stage(
                stage="embed",
                seconds=time.perf_counter() - started,
                outcome="timeout" if isinstance(exc, TimeoutError) else "error",
            )
            logger.warning("query embedding failed; retrieval cannot proceed", exc_info=True)
            raise RetrievalUnavailableError("query embedding failed") from exc
        record_retrieval_stage(stage="embed", seconds=time.perf_counter() - started)

        # 2) Hybrid retrieval (dense + sparse → RRF) — top hybrid_k chunks.
        hybrid_candidates = await self._hybrid.retrieve(
            query,
            k=self._hybrid_k,
            query_embedding=query_embedding,
            tenant_id=tenant_id,
        )

        # 3) Dedup by anime (one chunk per mal_id).
        deduped = _dedup_by_anime(hybrid_candidates)

        # 4) Rerank with cross-encoder; keep top rerank_k.
        # The reranker is sync + CPU-bound: run it in a thread (so it doesn't block
        # the event loop) with a timeout. On failure/timeout, skip reranking and keep
        # the hybrid order — degraded relevance beats a failed request.
        #
        # READ THE TIMER BELOW CAREFULLY. It spans the whole `await`, so it measures
        # thread handoff + the model + the wait to be rescheduled on the event loop.
        # That is CORRECT for a user-facing number — it is what the caller waits — but
        # it is NOT model latency, and reading it as such is a trap this repo has
        # already fallen into. Measured 2026-09-20: model 0.056s, this timer 1.250s p50.
        # For the model's own cost see anime.retrieval.rerank.compute (recorded inside
        # BgeReranker.score); for the gap's cause see anime.runtime.loop_lag.
        # Do not swap the reranker on the strength of THIS number alone.
        if deduped:
            started = time.perf_counter()
            try:
                rerank_scores = await asyncio.wait_for(
                    asyncio.to_thread(self._reranker.score, query, [c.text for c in deduped]),
                    timeout=self._rerank_timeout,
                )
                reranked = [
                    dataclasses.replace(c, rerank_score=s)
                    for c, s in zip(deduped, rerank_scores, strict=True)
                ]
                reranked.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)
                top_reranked = reranked[: self._rerank_k]
                record_retrieval_stage(stage="rerank", seconds=time.perf_counter() - started)
            except Exception as exc:
                # THE routing signal: no rerank score means no confidence, which
                # means should_use_venue() fails safe to the hosted chain. Before
                # this line, that only existed as a log message (see L.15).
                record_retrieval_stage(
                    stage="rerank",
                    seconds=time.perf_counter() - started,
                    outcome="timeout" if isinstance(exc, TimeoutError) else "error",
                )
                logger.warning("reranker failed/timed out; falling back to hybrid order")
                top_reranked = deduped[: self._rerank_k]
        else:
            top_reranked = []

        if not top_reranked:
            return []

        # 5) Fetch embeddings for MMR diversity computation.
        emb_map = await _fetch_embeddings(self._session, [c.key for c in top_reranked])
        emb_list = [emb_map[c.key] for c in top_reranked if c.key in emb_map]
        # If any embeddings are missing (shouldn't happen), drop those candidates.
        aligned = [c for c in top_reranked if c.key in emb_map]

        # 6) MMR → final_k. Assign final rank position.
        started = time.perf_counter()
        final = mmr_select(
            aligned,
            query_embedding,
            emb_list,
            k=self._final_k,
            lambda_=self._mmr_lambda,
        )
        record_retrieval_stage(stage="mmr", seconds=time.perf_counter() - started)
        return [dataclasses.replace(c, rank=i + 1) for i, c in enumerate(final)]
