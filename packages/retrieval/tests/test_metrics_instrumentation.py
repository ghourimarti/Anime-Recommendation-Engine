"""The call sites behind the dashboards must actually fire (Track O.4).

These are not tests of OpenTelemetry — metrics.py is a thin API wrapper and is
covered by packages/core/tests/test_otel.py. What can silently rot is the CALL
SITE: an instrument that exists, exports cleanly, and is never reached renders an
empty panel that reads exactly like "nothing is happening".
"""

from __future__ import annotations

import pytest
from anime_core.embeddings import EmbedResult
from anime_core.schemas import RecommendationResult
from anime_core.vector_index import VectorMatch
from anime_retrieval import cached_service as cached_mod
from anime_retrieval import hybrid as hybrid_mod
from anime_retrieval.cached_service import CachedRecommendationService
from anime_retrieval.hybrid import HybridRetriever
from anime_retrieval.sparse import BM25Match


class FakeCache:
    def __init__(self, stored: dict | None = None) -> None:
        self.stored = stored

    async def get(self, *, tenant, query):  # type: ignore[no-untyped-def]
        return self.stored

    async def set(self, *, tenant, query, value):  # type: ignore[no-untyped-def]
        self.stored = value


class FakeInner:
    async def recommend(self, query, *, tenant_id=None):  # type: ignore[no-untyped-def]
        return RecommendationResult(items=[])

    async def astream(self, query, *, tenant_id=None):  # type: ignore[no-untyped-def]
        yield "token"


class DummyEmbedder:
    @property
    def model(self) -> str:
        return "d"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


class OkVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [VectorMatch(mal_id=1, chunk_index=0, text="a1", score=0.9)]


class DownVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("pgvector down")


class SlowVector:
    """Outlives the retriever's timeout, so the leg is cancelled."""

    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        import asyncio

        await asyncio.sleep(5)
        return []


class OkBM25:
    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [BM25Match(mal_id=2, chunk_index=0, text="a2", score=1.0)]


@pytest.fixture
def cache_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(cached_mod, "record_cache_lookup", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture
def stage_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(hybrid_mod, "record_retrieval_stage", lambda **kw: calls.append(kw))
    return calls


@pytest.mark.asyncio
async def test_cache_hit_and_miss_are_both_recorded(cache_calls: list[dict]) -> None:
    """Hit rate needs BOTH sides: recording only hits makes a dead cache look perfect."""
    miss = CachedRecommendationService(inner=FakeInner(), response_cache=FakeCache(None))
    await miss.recommend("q")
    hit = CachedRecommendationService(
        inner=FakeInner(), response_cache=FakeCache(RecommendationResult(items=[]).model_dump())
    )
    await hit.recommend("q")

    assert [c["hit"] for c in cache_calls] == [False, True]
    assert {c["path"] for c in cache_calls} == {"recommend"}


@pytest.mark.asyncio
async def test_streaming_cache_lookups_are_recorded_under_their_own_path(
    cache_calls: list[dict],
) -> None:
    svc = CachedRecommendationService(inner=FakeInner(), response_cache=FakeCache(None))
    [token async for token in svc.astream("q")]
    assert cache_calls == [{"hit": False, "path": "stream"}]


@pytest.mark.asyncio
async def test_healthy_legs_record_their_duration(stage_calls: list[dict]) -> None:
    r = HybridRetriever(vector_index=OkVector(), bm25_index=OkBM25(), embedder=DummyEmbedder())
    await r.retrieve("q", query_embedding=[1.0, 0.0])

    assert [c["stage"] for c in stage_calls] == ["dense", "sparse"]
    assert all(c["seconds"] >= 0 for c in stage_calls)
    assert all(c.get("outcome", "ok") == "ok" for c in stage_calls)


@pytest.mark.asyncio
async def test_failed_leg_is_recorded_with_the_time_it_burned(stage_calls: list[dict]) -> None:
    """A leg that fails still costs latency; omitting it would make it look free."""
    r = HybridRetriever(vector_index=DownVector(), bm25_index=OkBM25(), embedder=DummyEmbedder())
    await r.retrieve("q", query_embedding=[1.0, 0.0])

    dense = next(c for c in stage_calls if c["stage"] == "dense")
    assert dense["outcome"] == "error"
    assert dense["seconds"] >= 0


@pytest.mark.asyncio
async def test_timed_out_leg_is_labelled_timeout_not_error(stage_calls: list[dict]) -> None:
    """The distinction drives the response: a timeout is a budget problem, an error is a bug."""
    r = HybridRetriever(
        vector_index=SlowVector(),
        bm25_index=OkBM25(),
        embedder=DummyEmbedder(),
        timeout_seconds=0.05,
    )
    await r.retrieve("q", query_embedding=[1.0, 0.0])

    dense = next(c for c in stage_calls if c["stage"] == "dense")
    assert dense["outcome"] == "timeout"
    assert dense["seconds"] >= 0.05  # it burned the whole budget
