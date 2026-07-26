"""Tests for service-level degradation — mocked, offline."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.resilience import RetrievalUnavailableError
from anime_core.schemas import Recommendation, Recommendations
from anime_retrieval.service import RecommendationService
from anime_retrieval.types import Candidate


def _cand(mal_id: int) -> Candidate:
    return Candidate(mal_id=mal_id, chunk_index=0, text=f"Title: Anime {mal_id}\n\nsynopsis")


class OkRetriever:
    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]:
        return [_cand(1), _cand(2)]


class DownRetriever:
    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]:
        raise RetrievalUnavailableError("both legs down")


class DownLLM:
    @property
    def model(self) -> str:
        return "down"

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        raise RuntimeError("all tiers failed")

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        raise RuntimeError("all tiers failed")
        yield ""  # pragma: no cover


class OkLLM:
    @property
    def model(self) -> str:
        return "ok"

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        return Recommendations(
            items=[Recommendation(mal_id=1, title="Anime 1", summary="s", why_match="w")]
        )

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        yield "ok"


@pytest.mark.asyncio
async def test_llm_all_down_degrades_to_popular() -> None:
    svc = RecommendationService(retriever=OkRetriever(), llm=DownLLM())
    result = await svc.recommend("q")
    assert result.degraded
    assert not result.is_empty  # popular fallback, not a 500


@pytest.mark.asyncio
async def test_retrieval_unavailable_degrades_to_popular() -> None:
    svc = RecommendationService(retriever=DownRetriever(), llm=OkLLM())
    result = await svc.recommend("q")
    assert result.degraded
    assert not result.is_empty


@pytest.mark.asyncio
async def test_kill_switch_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    svc = RecommendationService(retriever=OkRetriever(), llm=OkLLM())
    result = await svc.recommend("q")
    assert result.degraded  # kill switch → popular, LLM never called


@pytest.mark.asyncio
async def test_happy_path_not_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    svc = RecommendationService(retriever=OkRetriever(), llm=OkLLM())
    result = await svc.recommend("q")
    assert not result.degraded
    assert [r.mal_id for r in result.items] == [1]


@pytest.mark.asyncio
async def test_astream_llm_failure_degrades_not_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A streaming LLM outage must yield the degraded notice, NOT raise — else the
    SSE connection breaks and the browser shows a raw 'Failed to fetch'."""
    from anime_core.fallback import DEGRADED_NOTICE

    monkeypatch.setenv("LLM_ENABLED", "true")
    svc = RecommendationService(retriever=OkRetriever(), llm=DownLLM())
    tokens = [t async for t in svc.astream("q")]  # must not raise
    assert tokens == [DEGRADED_NOTICE]
