"""The title-existence check: the deterministic half of the I.F6 fix.

Every case here is a real measured one. The corpus names are exactly as this
deployment stores them — Japanese where the corpus is Japanese, because that is the
detail that breaks a naive string compare.
"""

from __future__ import annotations

import pytest
from anime_retrieval.catalog import (
    MATCH_CUTOFF,
    TitleCatalog,
    extract_named_titles,
    refusal_for,
)

# A slice of the real 269, chosen for the cases that matter: two stored under
# Japanese names whose English forms are what a user would actually type.
CATALOG = TitleCatalog(
    names=(
        "Cowboy Bebop",
        "Cowboy Bebop: Tengoku no Tobira",
        "Monster",
        "Kenpuu Denki Berserk",  # "Berserk"
        "Neon Genesis Evangelion",  # "Evangelion"
        "Slam Dunk",
        "Mobile Suit Gundam Wing",
        "Full Moon wo Sagashite",
    )
)


@pytest.mark.parametrize(
    "query,expected",
    [
        ("tell me about Cowboy Bebop", ["Cowboy Bebop"]),
        ("recommend me Monster", ["Monster"]),
        ("anime like Berserk", ["Berserk"]),
        ("is Slam Dunk any good", ["Slam Dunk"]),
        ("tell me about Demon Slayer and Jujutsu Kaisen", ["Demon Slayer", "Jujutsu Kaisen"]),
        # Descriptive queries name nothing. This is the important negative: the moment
        # this starts returning a "title", the product refuses real users.
        ("a samurai story that is also about revenge", []),
        ("psychological thriller with an unreliable narrator", []),
        ("something with beautiful animation and almost no dialogue", []),
        ("what is the capital of France", []),
    ],
)
def test_extract_named_titles(query: str, expected: list[str]) -> None:
    assert extract_named_titles(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "tell me about Demon Slayer and Jujutsu Kaisen",
        "recommend me Demon Slayer",
        "is Jujutsu Kaisen any good",
        "tell me about Chainsaw Man",
        "anime like Attack on Titan",
        "tell me about Spy x Family",
        "recommend me Frieren",
    ],
)
def test_absent_titles_are_reported_missing(query: str) -> None:
    """The I.F6 class. Each of these previously got three unrelated titles back."""
    assert CATALOG.missing_titles(query), f"{query!r} names nothing in the catalogue"


@pytest.mark.parametrize(
    "query",
    [
        "tell me about Cowboy Bebop",
        "recommend me Monster",
        "is Slam Dunk any good",
        "tell me about Neon Genesis Evangelion",
        # The two that a plain string compare gets wrong: stored under Japanese names.
        "anime like Berserk",  # Kenpuu Denki Berserk
        "recommend me Evangelion",  # Neon Genesis Evangelion
        "anime like Gundam Wing",  # Mobile Suit Gundam Wing
        # Names nothing at all — must never be treated as a missing title.
        "a samurai story that is also about revenge",
        "anime with a bittersweet ending that made you cry",
    ],
)
def test_present_or_unnamed_titles_are_not_missing(query: str) -> None:
    assert CATALOG.missing_titles(query) == []


def test_japanese_stored_titles_match_on_tokens_not_whole_string() -> None:
    """Why token containment exists, stated as a number.

    Whole-string similarity reads ~0.55 for "Berserk" against "Kenpuu Denki Berserk" —
    below any usable cutoff — while the title is plainly present. Containment reads
    1.00. Drop containment and the check starts refusing the catalogue's own contents.
    """
    import difflib

    from anime_retrieval.catalog import _normalise

    whole_string = difflib.SequenceMatcher(
        None, _normalise("Berserk"), _normalise("Kenpuu Denki Berserk")
    ).ratio()

    assert whole_string < MATCH_CUTOFF, "premise changed: whole-string now clears the cutoff"
    assert CATALOG.best_match("Berserk") == 1.0


def test_cutoff_sits_inside_the_measured_gap() -> None:
    """Regression guard on the calibrated number.

    Measured over 18 queries: present titles score 1.00, absent ones top out at 0.63.
    The cutoff belongs between those, and the margin is why this check is trusted where
    the confidence floor is only a safety net.
    """
    present = min(CATALOG.best_match(t) for t in ("Cowboy Bebop", "Berserk", "Evangelion"))
    absent = max(CATALOG.best_match(t) for t in ("Demon Slayer", "Jujutsu Kaisen", "Frieren"))

    assert absent < MATCH_CUTOFF < present, (
        f"cutoff {MATCH_CUTOFF} no longer separates absent ({absent:.2f}) from "
        f"present ({present:.2f}) — re-calibrate before changing it"
    )


def test_refusal_names_every_missing_title() -> None:
    """A refusal that mentions one of two titles reads like the other was found."""
    missing = CATALOG.missing_titles("tell me about Demon Slayer and Jujutsu Kaisen")
    message = refusal_for(missing)

    assert "Demon Slayer" in message and "Jujutsu Kaisen" in message


def test_empty_catalog_never_refuses() -> None:
    """Fail OPEN. An empty catalogue means "not loaded", not "nothing exists"."""
    assert TitleCatalog(names=()).missing_titles("tell me about Cowboy Bebop") == []
