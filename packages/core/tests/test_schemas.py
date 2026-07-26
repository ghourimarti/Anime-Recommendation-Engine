"""Tests for the recommendation structured-output schema."""

from __future__ import annotations

from anime_core.schemas import MAX_RECOMMENDATIONS, Recommendation, Recommendations


def _rec(mal_id: int) -> Recommendation:
    return Recommendation(
        mal_id=mal_id, title=f"Anime {mal_id}", summary="A summary.", why_match="It fits."
    )


def test_empty_recommendations() -> None:
    r = Recommendations()
    assert r.is_empty
    assert r.items == []


def test_recommendations_capped() -> None:
    r = Recommendations(items=[_rec(i) for i in range(10)])
    assert len(r.items) == MAX_RECOMMENDATIONS
    assert not r.is_empty


def test_recommendation_roundtrip() -> None:
    r = _rec(20)
    assert r.mal_id == 20
    assert r.title == "Anime 20"
    # field presence is enforced by Pydantic; constructing without them would raise
