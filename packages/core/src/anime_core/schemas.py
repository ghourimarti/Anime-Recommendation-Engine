"""Structured-output contract for anime recommendations.

This is the typed boundary between the LLM and everything downstream (API,
storage, eval). The LLM is asked to emit this shape via
`llm.with_structured_output(Recommendations)`; the field descriptions below are
fed to the model as the function/JSON schema, so they double as prompt content.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_RECOMMENDATIONS = 5


class Recommendation(BaseModel):
    """One anime recommendation, grounded in a retrieved candidate."""

    mal_id: int = Field(
        description="The exact MyAnimeList ID copied verbatim from the candidate. Never invent one."
    )
    title: str = Field(description="The anime title.")
    summary: str = Field(description="A concise 2-3 sentence plot summary.")
    why_match: str = Field(
        description="One or two sentences explaining why this anime matches the user's request."
    )


class Recommendations(BaseModel):
    """The model's structured answer: recommendations, OR a refusal.

    `refusal` is what lets the model say "I can't answer this". Without it the schema
    offered exactly one way to respond — a list of anime — and the prompt asked for
    "exactly 3", so the model dutifully produced three for *any* input. Measured:
    "what is the capital of France" returned Noir, Gankutsuou and Yakitate!! Japan;
    "how do I file my taxes" returned three sports anime.

    That isn't the model misbehaving. A model given no way to decline will not
    invent one — it fills the shape you hand it. The refusal has to exist in the
    schema before the model can choose it.
    """

    items: list[Recommendation] = Field(
        default_factory=list,
        description=(
            "Recommended anime, best match first. Aim for 3 when the request is a "
            "genuine anime recommendation request AND the candidates genuinely fit. "
            "Leave EMPTY when refusing."
        ),
    )
    refusal: str | None = Field(
        default=None,
        description=(
            "Set this INSTEAD of items when you cannot answer: the request is not "
            "asking for anime recommendations (e.g. general knowledge, coding help, "
            "tax advice), or no candidate genuinely matches the request. One short, "
            "friendly sentence explaining why. Never pad the list to reach 3 — an "
            "irrelevant recommendation is worse than an honest refusal."
        ),
    )

    @field_validator("items")
    @classmethod
    def _cap(cls, value: list[Recommendation]) -> list[Recommendation]:
        # Be permissive on count (robustness) but never let a runaway response
        # blow past a sane ceiling. The "aim for 3" target is a prompt instruction,
        # not a hard schema constraint — hard-failing on count makes the app brittle.
        return value[:MAX_RECOMMENDATIONS]

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def is_refusal(self) -> bool:
        """A refusal is an EMPTY answer with a stated reason.

        Items win if the model somehow sets both: a populated list means it found
        something, and we'd rather show a recommendation with a stray refusal string
        than hide real results behind one.
        """
        return not self.items and bool(self.refusal)


class RecommendationResult(BaseModel):
    """Service-layer result: recommendations + refusal + degradation metadata.

    Separate from `Recommendations` (the LLM-output schema) so the LLM is never
    asked to fill `degraded`/`notice`, and so a degraded answer can be excluded
    from the cache — never cache an outage response.

    `refusal` and `degraded` are NOT the same thing, and conflating them would be a
    real bug:
      - refusal  = "I understood you, and the honest answer is that I have nothing
                    for you." The system is healthy. Caching it is correct.
      - degraded = "Something is broken and this answer is worse than it should be."
                    Never cached, and it should page someone.
    """

    items: list[Recommendation] = Field(default_factory=list)
    refusal: str | None = None
    degraded: bool = False
    notice: str | None = None

    @classmethod
    def of(cls, recs: Recommendations) -> RecommendationResult:
        """Wrap a successful LLM result (not degraded)."""
        return cls(items=recs.items, refusal=recs.refusal if recs.is_refusal else None)

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def is_refusal(self) -> bool:
        return not self.items and bool(self.refusal)
