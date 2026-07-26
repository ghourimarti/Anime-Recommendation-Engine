"""Static "popular anime" fallback — the zero-dependency last resort.

When the LLM tier is exhausted or retrieval is fully down, the user still gets a
sensible answer instead of a 500. This list is STATIC on purpose: the database or
a provider may be exactly what's failing, so the ultimate fallback must not depend
on either. the housekeeping job precomputes a fresher "popular this week"
into Redis; this remains the floor beneath that.

mal_ids/titles are real corpus entries so the frontend's source links still work.
"""

from __future__ import annotations

from anime_core.schemas import Recommendation, RecommendationResult

DEGRADED_NOTICE = (
    "We couldn't generate tailored recommendations right now — here are some "
    "widely loved anime while we recover."
)
NO_MATCH_NOTICE = (
    "We didn't find strong matches for that — here are some popular anime you might enjoy."
)

_POPULAR: tuple[Recommendation, ...] = (
    Recommendation(
        mal_id=1,
        title="Cowboy Bebop",
        summary="A ragtag crew of bounty hunters drifts across the solar system chasing "
        "criminals and their own pasts.",
        why_match="A near-universally loved classic — a safe, excellent starting point.",
    ),
    Recommendation(
        mal_id=19,
        title="Monster",
        summary="A brilliant surgeon hunts a charismatic killer he once saved, across a "
        "tense psychological cat-and-mouse.",
        why_match="One of the most acclaimed thrillers in the medium.",
    ),
    Recommendation(
        mal_id=21,
        title="One Piece",
        summary="A young pirate and his crew sail a vast world chasing the ultimate "
        "treasure and their dreams.",
        why_match="A long-running, beloved adventure with broad appeal.",
    ),
)


def popular_fallback(notice: str = DEGRADED_NOTICE) -> RecommendationResult:
    """Return the static popular set as a degraded result."""
    return RecommendationResult(items=list(_POPULAR), degraded=True, notice=notice)
