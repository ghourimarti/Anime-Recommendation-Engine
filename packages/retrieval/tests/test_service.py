"""Tests for RecommendationService — retrieval + generation + grounding, mocked."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.schemas import Recommendation, Recommendations
from anime_retrieval.service import (
    RecommendationService,
    build_context,
    ground_recommendations,
)
from anime_retrieval.types import Candidate


class FakeRetriever:
    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = candidates

    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]:
        return self._candidates


class FakeLLM:
    """Returns a fixed Recommendations (possibly with a hallucinated mal_id)."""

    def __init__(self, recs: Recommendations) -> None:
        self._recs = recs

    @property
    def model(self) -> str:
        return "fake"

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        return self._recs

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        yield "streamed answer"


def _cand(mal_id: int) -> Candidate:
    return Candidate(mal_id=mal_id, chunk_index=0, text=f"Title: Anime {mal_id}\n\nsynopsis")


def _rec(mal_id: int) -> Recommendation:
    return Recommendation(mal_id=mal_id, title=f"Anime {mal_id}", summary="s", why_match="w")


def test_build_context_tags_mal_ids() -> None:
    ctx = build_context([_cand(1), _cand(5)])
    assert "[mal_id=1]" in ctx
    assert "[mal_id=5]" in ctx


@pytest.mark.asyncio
async def test_recommend_grounds_valid_ids() -> None:
    candidates = [_cand(1), _cand(2), _cand(3)]
    llm = FakeLLM(Recommendations(items=[_rec(1), _rec(2), _rec(3)]))
    svc = RecommendationService(retriever=FakeRetriever(candidates), llm=llm)
    result = await svc.recommend("q")
    assert [r.mal_id for r in result.items] == [1, 2, 3]


@pytest.mark.asyncio
async def test_recommend_drops_hallucinated_id() -> None:
    candidates = [_cand(1), _cand(2)]
    # LLM hallucinates mal_id 999 with a title that matches NOTHING → must be dropped
    bogus = Recommendation(mal_id=999, title="Totally Made Up", summary="s", why_match="w")
    llm = FakeLLM(Recommendations(items=[_rec(1), bogus, _rec(2)]))
    svc = RecommendationService(retriever=FakeRetriever(candidates), llm=llm)
    result = await svc.recommend("q")
    assert [r.mal_id for r in result.items] == [1, 2]


def test_ground_recovers_wrong_id_by_title() -> None:
    # candidate _cand(19) has text "Title: Anime 19\n\nsynopsis"
    candidates = [_cand(19), _cand(20)]
    # LLM picked the right anime (title "Anime 19") but botched the id (returned 0)
    wrong_id = Recommendation(mal_id=0, title="Anime 19", summary="s", why_match="w")
    grounded = ground_recommendations(Recommendations(items=[wrong_id]), candidates)
    # title-match canonicalizes the id back to 19 instead of dropping the rec
    assert [r.mal_id for r in grounded.items] == [19]


@pytest.mark.asyncio
async def test_recommend_no_candidates_degrades_to_popular() -> None:
    # No retrieval hits → degrade to the popular fallback, not an empty result.
    llm = FakeLLM(Recommendations(items=[_rec(1)]))
    svc = RecommendationService(retriever=FakeRetriever([]), llm=llm)
    result = await svc.recommend("q")
    assert result.degraded
    assert not result.is_empty


@pytest.mark.asyncio
async def test_astream_yields_tokens() -> None:
    svc = RecommendationService(
        retriever=FakeRetriever([_cand(1)]),
        llm=FakeLLM(Recommendations(items=[_rec(1)])),
    )
    out = [t async for t in svc.astream("q")]
    assert out == ["streamed answer"]


@pytest.mark.asyncio
async def test_astream_no_candidates_yields_notice() -> None:
    # No retrieval hits → stream a friendly no-match notice, not silence.
    from anime_core.fallback import NO_MATCH_NOTICE

    svc = RecommendationService(
        retriever=FakeRetriever([]),
        llm=FakeLLM(Recommendations(items=[_rec(1)])),
    )
    out = [t async for t in svc.astream("q")]
    assert out == [NO_MATCH_NOTICE]
