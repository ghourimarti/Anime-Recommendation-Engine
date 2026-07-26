"""API wire models — the HTTP boundary contract.

Deliberately separate from the internal `anime_core.schemas.Recommendation` and
the ORM models: the wire shape is owned by the API and can evolve independently
of internals. `RecommendationOut.from_core` is the single conversion point.
"""

from __future__ import annotations

from datetime import datetime

from anime_core.schemas import Recommendation
from pydantic import BaseModel, Field, field_validator


class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class RecommendationOut(BaseModel):
    mal_id: int
    title: str
    summary: str
    why_match: str

    @classmethod
    def from_core(cls, rec: Recommendation) -> RecommendationOut:
        return cls(
            mal_id=rec.mal_id,
            title=rec.title,
            summary=rec.summary,
            why_match=rec.why_match,
        )


class RecommendResponse(BaseModel):
    query: str
    query_history_id: int
    recommendations: list[RecommendationOut]
    # Set when the request was DECLINED: out-of-scope (general knowledge, coding help,
    # an injection attempt) or nothing in the corpus genuinely matched. recommendations
    # is empty and this explains why.
    #
    # Distinct from `degraded` on purpose. A refusal means the system is healthy and
    # the honest answer is "nothing" — still HTTP 200, because the request was served
    # correctly; the answer just isn't a list of anime. Before this existed, the model
    # had no way to decline and confabulated three anime for "what is the capital of
    # France".
    refusal: str | None = None
    # True when the result is a degraded fallback (LLM/retrieval down, kill switch,
    # or no strong matches). The frontend surfaces `notice` so degradation is honest.
    degraded: bool = False
    notice: str | None = None


class FeedbackRequest(BaseModel):
    query_history_id: int | None = None
    mal_id: int
    rating: int

    @field_validator("rating")
    @classmethod
    def _validate_rating(cls, value: int) -> int:
        if value not in (-1, 1):
            raise ValueError("rating must be 1 (up) or -1 (down)")
        return value


class FeedbackResponse(BaseModel):
    id: int
    status: str = "recorded"


class HistoryItem(BaseModel):
    id: int
    query: str
    recommendations: list[RecommendationOut]
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
