"""CachedRecommendationService — response cache around the service.

Lookup order:
  1. Response cache (NORMALIZED query hash)  -> instant, no embed, no LLM.
  2. Miss -> inner.recommend(); populate the cache (never cache a degraded result).

There used to be a second stage — a semantic cache keyed on embedding cosine — and
it is gone. Measured on real query pairs, meaning-inverted near-misses ("strong
female lead" vs "strong male lead", cosine 0.863) score HIGHER than genuine
paraphrases (max 0.838), so no threshold could admit a paraphrase without also
serving the opposite of what was asked. See anime_core.caches for the numbers.

The response cache now normalizes its key, which captures the realistic
near-duplicate ("Show me sports anime!" vs "show me sports anime") deterministically
and cannot ever hand back an answer to a different question.

Streaming caching is intentionally limited in v1: astream replays the response
cache as text on a hit, otherwise delegates to the inner stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from anime_core.caches import ResponseCache
from anime_core.observability.metrics import record_cache_lookup
from anime_core.schemas import RecommendationResult


class Recommender(Protocol):
    """The recommend + stream contract (RecommendationService satisfies it)."""

    async def recommend(
        self, query: str, *, tenant_id: str | None = None
    ) -> RecommendationResult: ...
    def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]: ...


class CachedRecommendationService:
    """Decorates a Recommender with normalized-query response caching."""

    def __init__(
        self,
        *,
        inner: Recommender,
        response_cache: ResponseCache,
    ) -> None:
        self._inner = inner
        self._response = response_cache

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        cached = await self._response.get(tenant=tenant_id, query=query)
        record_cache_lookup(hit=cached is not None, path="recommend")
        if cached is not None:
            return RecommendationResult.model_validate(cached)

        result = await self._inner.recommend(query, tenant_id=tenant_id)
        # Cache ONLY non-degraded results. Caching a degraded answer would pin an
        # outage in place for the full TTL, long after the outage itself is over.
        if not result.degraded:
            await self._response.set(tenant=tenant_id, query=query, value=result.model_dump())
        return result

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        cached = await self._response.get(tenant=tenant_id, query=query)
        record_cache_lookup(hit=cached is not None, path="stream")
        if cached is not None:
            result = RecommendationResult.model_validate(cached)
            for rec in result.items:
                yield f"{rec.title}: {rec.why_match}\n"
            return
        async for token in self._inner.astream(query, tenant_id=tenant_id):
            yield token
