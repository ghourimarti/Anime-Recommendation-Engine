"""Tests for CachedRecommendationService — a response-cache hit must skip the inner service.

The semantic-cache stage this class used to have is gone, and its test is worth a
post-mortem. test_semantic_hit_skips_inner used a FixedEmbedder that returned the
SAME vector for every input, so any two queries were "semantically identical" by
construction. It asserted that a semantic hit skipped the LLM — and it did, because
the test had made the two queries literally the same point in vector space.

The test hard-coded the very assumption it was supposed to be checking. In
production, with real embeddings, paraphrases never got close to the 0.92 threshold
(0.656-0.838) while meaning-inverted pairs did (0.863) — so the cache never fired,
and could not have fired safely. See anime_core.caches for the measurement.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.cache import InMemoryCache
from anime_core.caches import ResponseCache
from anime_core.schemas import Recommendation, RecommendationResult
from anime_retrieval.cached_service import CachedRecommendationService


class FakeInner:
    """Counts recommend calls; returns a fixed result."""

    def __init__(self, result: RecommendationResult) -> None:
        self._result = result
        self.recommend_calls = 0

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        self.recommend_calls += 1
        return self._result

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        yield "inner-stream"


def _make(
    recs_items: list[int], *, degraded: bool = False
) -> tuple[CachedRecommendationService, FakeInner]:
    cache = InMemoryCache()
    result = RecommendationResult(
        items=[
            Recommendation(mal_id=i, title=f"A{i}", summary="s", why_match="w") for i in recs_items
        ],
        degraded=degraded,
    )
    inner = FakeInner(result)
    svc = CachedRecommendationService(inner=inner, response_cache=ResponseCache(cache))
    return svc, inner


@pytest.mark.asyncio
async def test_miss_then_hit_skips_inner() -> None:
    svc, inner = _make([1, 2])
    r1 = await svc.recommend("thriller")
    assert [r.mal_id for r in r1.items] == [1, 2]
    assert inner.recommend_calls == 1

    r2 = await svc.recommend("thriller")
    assert [r.mal_id for r in r2.items] == [1, 2]
    assert inner.recommend_calls == 1  # served from cache — no second LLM call


@pytest.mark.asyncio
async def test_trivial_rewording_hits_the_cache() -> None:
    """Punctuation/case/whitespace variants are the SAME request and must hit.

    This is the realistic near-duplicate, and the only one we can serve safely.
    """
    svc, inner = _make([7])
    await svc.recommend("Show me sports anime!")
    assert inner.recommend_calls == 1

    r = await svc.recommend("  show me   sports anime ")
    assert [x.mal_id for x in r.items] == [7]
    assert inner.recommend_calls == 1  # inner NOT called again


@pytest.mark.asyncio
async def test_opposite_meaning_does_not_hit_the_cache() -> None:
    """The regression test for the wrong-answer risk.

    Cosine rates these two 0.863 — higher than any genuine paraphrase — so the old
    semantic cache, at any threshold low enough to ever fire, would have answered
    "strong male lead" with the results for "strong female lead". The inner service
    MUST be called again.
    """
    svc, inner = _make([7])
    await svc.recommend("anime with a strong female lead")
    assert inner.recommend_calls == 1

    await svc.recommend("anime with a strong male lead")
    assert inner.recommend_calls == 2, "a different question must not be served from cache"


@pytest.mark.asyncio
async def test_degraded_results_are_never_cached() -> None:
    """Caching a degraded answer pins an outage in place for the whole TTL."""
    svc, inner = _make([1], degraded=True)
    await svc.recommend("comedy")
    await svc.recommend("comedy")
    assert inner.recommend_calls == 2  # never cached, so it retried


@pytest.mark.asyncio
async def test_tenant_isolation() -> None:
    """One user's cached answer must never be served to another."""
    svc, inner = _make([1])
    await svc.recommend("comedy", tenant_id="user-a")
    assert inner.recommend_calls == 1
    await svc.recommend("comedy", tenant_id="user-b")
    assert inner.recommend_calls == 2


@pytest.mark.asyncio
async def test_astream_replays_response_cache() -> None:
    svc, _inner = _make([1])
    await svc.recommend("comedy")  # populates response cache
    tokens = [t async for t in svc.astream("comedy")]
    assert tokens  # replayed from cache
    assert "A1" in "".join(tokens)
