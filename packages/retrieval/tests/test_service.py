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


# ─── confidence floor (I.F6 / I.13) ───────────────────────────────────────────
def _scored(mal_id: int, score: float) -> Candidate:
    return Candidate(
        mal_id=mal_id,
        chunk_index=0,
        text=f"Title: Anime {mal_id}\n\nsynopsis",
        rerank_score=score,
    )


class CountingLLM(FakeLLM):
    """Records whether the LLM was reached at all."""

    def __init__(self, recs: Recommendations) -> None:
        super().__init__(recs)
        self.calls = 0

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self.calls += 1
        return await super().recommend(query=query, context=context)


@pytest.mark.asyncio
async def test_confidence_below_floor_refuses_without_calling_the_llm() -> None:
    """The floor exists so the answer does not depend on WHICH tier served it.

    Measured 2026-09-20: on one out-of-scope query Groq refused 9/9 while the
    gpt-4o-mini fallback answered 3/3. Deciding in code removes the model from the
    decision entirely -- and an out-of-scope question stops costing a generation.
    """
    llm = CountingLLM(Recommendations(items=[_rec(1)]))
    svc = RecommendationService(retriever=FakeRetriever([_scored(1, -20.0)]), llm=llm)

    result = await svc.recommend("what is the capital of France")

    assert result.items == []
    assert result.refusal, "must carry a refusal, not an empty answer"
    assert llm.calls == 0, "the LLM must not be reached at all below the floor"


@pytest.mark.asyncio
async def test_confidence_above_floor_still_reaches_the_llm() -> None:
    """The positive control. A floor that swallows normal traffic is worse than none."""
    llm = CountingLLM(Recommendations(items=[_rec(1)]))
    svc = RecommendationService(retriever=FakeRetriever([_scored(1, -4.0)]), llm=llm)

    result = await svc.recommend("a samurai story that is also about revenge")

    assert llm.calls == 1
    assert [i.mal_id for i in result.items] == [1]


@pytest.mark.asyncio
async def test_missing_confidence_fails_open() -> None:
    """None means the reranker did not RUN, not that the match is poor.

    RERANK_TIMEOUT is 2.0s and a cold start blows it, so None is routine. Treating
    it as "no confidence" would turn a slow host into a refusal storm -- the whole
    product declining while retrieval is merely warming up.
    """
    llm = CountingLLM(Recommendations(items=[_rec(1)]))
    svc = RecommendationService(retriever=FakeRetriever([_cand(1)]), llm=llm)  # no rerank_score

    result = await svc.recommend("anything at all")

    assert llm.calls == 1, "a missing score must not refuse"
    assert [i.mal_id for i in result.items] == [1]


@pytest.mark.asyncio
async def test_stream_applies_the_same_floor() -> None:
    """Both entry points must refuse the same things, or streaming is the lenient one."""
    from anime_retrieval.service import OUT_OF_SCOPE_REFUSAL

    llm = CountingLLM(Recommendations(items=[_rec(1)]))
    svc = RecommendationService(retriever=FakeRetriever([_scored(1, -20.0)]), llm=llm)

    chunks = [c async for c in svc.astream("what is the capital of France")]

    assert chunks == [OUT_OF_SCOPE_REFUSAL]


def test_floor_is_below_every_measured_answerable_query() -> None:
    """Regression guard on the calibrated number itself.

    -11.0 was derived from 10 adversarial + 59 answerable golden queries. The
    nearest legitimate query measured -10.72 (from the HARD_ANSWERABLE over-refusal
    set), so the margin is 0.28 logit. Raising the floor past that starts refusing
    real users, and the two failure directions are measured in different places:
    refusal_recall in the refusal eval, false_refusal_rate right beside it.
    """
    from anime_retrieval.service import REFUSE_BELOW_CONFIDENCE

    assert REFUSE_BELOW_CONFIDENCE <= -11.0, (
        "floor raised above the calibrated value -- re-run the calibration over the "
        "golden set before changing it; at -9.5 it refuses 10% of answerable queries"
    )
