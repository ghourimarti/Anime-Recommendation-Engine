"""API wire-schema tests."""

from __future__ import annotations

import pytest
from anime_api.schemas import FeedbackRequest, RecommendationOut
from anime_core.schemas import Recommendation
from pydantic import ValidationError


def test_recommendation_out_from_core() -> None:
    core = Recommendation(mal_id=1, title="A", summary="s", why_match="w")
    out = RecommendationOut.from_core(core)
    assert out.mal_id == 1
    assert out.title == "A"


def test_feedback_rating_accepts_plus_minus_one() -> None:
    assert FeedbackRequest(mal_id=1, rating=1).rating == 1
    assert FeedbackRequest(mal_id=1, rating=-1).rating == -1


def test_feedback_rating_rejects_other() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(mal_id=1, rating=0)
