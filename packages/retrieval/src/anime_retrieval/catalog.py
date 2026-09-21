"""Does the query NAME a title this catalogue does not have?

This exists because retrieval confidence cannot answer that question. Confidence
measures "is anything here similar", and for "tell me about Demon Slayer" the answer
is a confident yes -- the corpus is full of shounen action, and the reranker
correctly finds it. Measured 2026-09-20, that query scores -4.339, HIGHER than the
median legitimate vague query (-4.843). Refusing it by confidence would mean
refusing about one real query in three.

So the signal has to be different in kind: the user named something, and either the
catalogue has it or it does not. That is a lookup, not a similarity score, and it is
deterministic -- which is the point. The same question previously got a refusal or
three unrelated recommendations depending on which LLM tier happened to serve it
(Groq refused 9/9, the gpt-4o-mini fallback answered 3/3 on identical input).

MATCHING, and why it is not a plain string compare
--------------------------------------------------
This corpus stores Japanese titles. "Berserk" is `Kenpuu Denki Berserk`, and
"Evangelion" is `Neon Genesis Evangelion`, so whole-string similarity reads 0.55 and
0.53 for titles that are plainly present. Token containment fixes exactly that: every
content word the user typed appears in the stored title. Measured over 18 queries:

    class                     score      outcome
    in-corpus titles (7)       1.00      answered
    absent titles (7)     0.45-0.63      refused
    descriptive (4)              --      no title extracted at all

MATCH_CUTOFF sits at 0.78, midway through a 0.37-wide gap. That margin is the reason
to prefer this over the confidence floor, whose nearest legitimate query sat 0.03
away.

KNOWN LIMIT: a user who types an English title for a show stored only under an
unrelated romaji name -- no shared words, so neither ratio nor containment fires --
is refused for a show the catalogue actually has. Nothing in the present corpus does
that, and the fix is an alias table, not a lower cutoff: lowering it re-admits the
absent titles this module exists to catch.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Midpoint of the measured gap (absent titles top out at 0.63, present ones hit 1.00).
MATCH_CUTOFF = 0.78

# Dropped before comparing: they carry no identity, and leaving them in lets a title
# match on "the" alone. Both English and romaji particles, because the corpus mixes
# them ("Kenpuu Denki Berserk", "Full Moon wo Sagashite").
_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "no", "wo", "ni", "to", "and", "in", "on", "season", "movie", "tv"}
)

# Phrases that mean "I am naming a specific show", with the name as group 1. Deliberately
# a small, literal set: a looser rule starts extracting titles out of descriptive queries
# ("something with beautiful animation") and refusing them, which is the failure mode
# this whole area is trying to avoid.
_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\btell me about (.+)$",
        r"\brecommend me (.+)$",
        r"\banime like (.+)$",
        r"\bsomething like (.+)$",
        r"\bis (.+?) (?:any good|good|worth watching)\b",
        r"\bhave you seen (.+)$",
        r"\bwhere can i watch (.+)$",
    )
)

# "Demon Slayer and Jujutsu Kaisen" is two titles, and refusing needs to name both --
# a refusal that mentions one of them reads like the other was found.
_SPLIT = re.compile(r"\s*(?:,|\band\b|&)\s*", re.IGNORECASE)


def _normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", folded)).strip()


def _content_tokens(text: str) -> set[str]:
    return {t for t in _normalise(text).split() if t not in _STOPWORDS}


def extract_named_titles(query: str) -> list[str]:
    """Titles the query explicitly names, or [] when it only describes what it wants."""
    cleaned = query.strip().rstrip("?.!")
    for pattern in _PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return [part.strip() for part in _SPLIT.split(match.group(1)) if part.strip()]
    return []


@dataclass(frozen=True)
class TitleCatalog:
    """The titles this deployment can actually talk about.

    Loaded once at startup rather than per request: it is 269 rows today and the set
    only changes on re-ingest. A stale catalogue after an ingest would refuse titles
    that now exist, so a restart is part of ingesting -- which is already true for the
    reranker weights baked into the image.
    """

    names: tuple[str, ...]

    def best_match(self, name: str) -> float:
        """0.0-1.0. The better of whole-string similarity and token containment."""
        normalised = _normalise(name)
        if not normalised:
            return 0.0
        tokens = _content_tokens(name)
        best = max(
            (difflib.SequenceMatcher(None, normalised, _normalise(t)).ratio() for t in self.names),
            default=0.0,
        )
        if tokens:
            best = max(
                best,
                max(
                    (len(tokens & _content_tokens(t)) / len(tokens) for t in self.names),
                    default=0.0,
                ),
            )
        return best

    def missing_titles(self, query: str) -> list[str]:
        """Named titles the catalogue does not have. [] means "nothing to object to".

        [] covers both "the user named titles and we have them" and "the user named
        nothing at all", because the caller does the same thing in both cases: carry on
        to the LLM. Only a non-empty result is a decision.

        An EMPTY catalogue fails open. No names loaded means "we do not know what we
        have", not "we have nothing" -- and the difference matters, because the
        fail-closed reading refuses every named title in the product. Caught by its own
        test rather than in production.
        """
        if not self.names:
            return []
        return [n for n in extract_named_titles(query) if self.best_match(n) < MATCH_CUTOFF]


def refusal_for(missing: list[str]) -> str:
    """Name what is missing. "I can't help with that" invites a retry of the same query."""
    titles = ", ".join(missing)
    return (
        f"This catalogue doesn't include {titles}, so I can't recommend or describe it. "
        "It covers classic anime up to the mid-2000s — tell me a genre, mood or premise "
        "and I'll find something in it."
    )


async def load_catalog(session: AsyncSession) -> TitleCatalog:
    """Read every title once, at startup.

    Best effort on purpose: a catalogue that fails to load yields an EMPTY one, which
    fails open (see missing_titles). Losing this check degrades the product to what it
    did before it existed; refusing to boot over it would be worse.
    """
    from anime_core.db.models import AnimeTitle
    from sqlalchemy import select

    try:
        rows = await session.execute(select(AnimeTitle.name))
        names = tuple(n for (n,) in rows.all() if n)
    except Exception as exc:  # never block startup on a lookup table
        logger.warning("title catalogue failed to load (%s); named-title check disabled", exc)
        return TitleCatalog(names=())
    logger.info("title catalogue loaded: %d titles", len(names))
    return TitleCatalog(names=names)
