"""Tests for HybridRetriever resilience — dense→sparse fallback, both-down → raise."""

from __future__ import annotations

import pytest
from anime_core.resilience import RetrievalUnavailableError
from anime_core.vector_index import VectorMatch
from anime_retrieval.hybrid import HybridRetriever
from anime_retrieval.sparse import BM25Match


class OkVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [VectorMatch(mal_id=1, chunk_index=0, text="a1", score=0.9)]


class DownVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("pgvector down")


class OkBM25:
    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [BM25Match(mal_id=2, chunk_index=0, text="a2", score=1.0)]


class DownBM25:
    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("FTS down")


class DummyEmbedder:
    @property
    def model(self) -> str:
        return "d"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        from anime_core.embeddings import EmbedResult

        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


def _retriever(vector, bm25) -> HybridRetriever:  # type: ignore[no-untyped-def]
    return HybridRetriever(vector_index=vector, bm25_index=bm25, embedder=DummyEmbedder())


@pytest.mark.asyncio
async def test_dense_down_falls_back_to_sparse_only() -> None:
    r = _retriever(DownVector(), OkBM25())
    results = await r.retrieve("q", query_embedding=[1.0, 0.0])
    assert [c.mal_id for c in results] == [2]  # sparse-only result


@pytest.mark.asyncio
async def test_sparse_down_uses_dense_only() -> None:
    r = _retriever(OkVector(), DownBM25())
    results = await r.retrieve("q", query_embedding=[1.0, 0.0])
    assert [c.mal_id for c in results] == [1]


@pytest.mark.asyncio
async def test_both_down_raises_retrieval_unavailable() -> None:
    r = _retriever(DownVector(), DownBM25())
    with pytest.raises(RetrievalUnavailableError):
        await r.retrieve("q", query_embedding=[1.0, 0.0])


# ── session recovery after a failed leg (L.16) ──────────────────────────────────
# Real-Postgres proof of the failure mode: tests/integration/test_session_recovery.py


class Recovery:
    """Stands in for session.rollback and records when it ran."""

    def __init__(self, events: list[str], *, fails: bool = False) -> None:
        self._events = events
        self._fails = fails
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1
        self._events.append("recover")
        if self._fails:
            raise RuntimeError("rollback failed")


class RecordingBM25:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        self._events.append("sparse")
        return [BM25Match(mal_id=2, chunk_index=0, text="a2", score=1.0)]


def _recovering(vector, bm25, hook: Recovery) -> HybridRetriever:  # type: ignore[no-untyped-def]
    return HybridRetriever(
        vector_index=vector, bm25_index=bm25, embedder=DummyEmbedder(), on_leg_failure=hook
    )


@pytest.mark.asyncio
async def test_failed_dense_leg_recovers_the_session_before_sparse_runs() -> None:
    events: list[str] = []
    hook = Recovery(events)
    results = await _recovering(DownVector(), RecordingBM25(events), hook).retrieve(
        "q", query_embedding=[1.0, 0.0]
    )
    assert events == ["recover", "sparse"]  # sparse must not run on the broken session
    assert [c.mal_id for c in results] == [2]


@pytest.mark.asyncio
async def test_both_legs_down_recover_after_each_then_raise() -> None:
    hook = Recovery([])
    with pytest.raises(RetrievalUnavailableError):
        await _recovering(DownVector(), DownBM25(), hook).retrieve("q", query_embedding=[1.0, 0.0])
    # The route still writes history after a degraded answer, so the session must
    # be usable even when the LAST leg is the one that failed.
    assert hook.calls == 2


@pytest.mark.asyncio
async def test_failing_recovery_hook_does_not_mask_the_fallback() -> None:
    hook = Recovery([], fails=True)
    results = await _recovering(DownVector(), OkBM25(), hook).retrieve(
        "q", query_embedding=[1.0, 0.0]
    )
    assert [c.mal_id for c in results] == [2]
    assert hook.calls == 1


@pytest.mark.asyncio
async def test_healthy_legs_never_call_the_recovery_hook() -> None:
    hook = Recovery([])
    results = await _recovering(OkVector(), OkBM25(), hook).retrieve(
        "q", query_embedding=[1.0, 0.0]
    )
    assert {c.mal_id for c in results} == {1, 2}
    assert hook.calls == 0
