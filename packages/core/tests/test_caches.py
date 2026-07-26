"""Tests for the typed caches (Embedding / Response).

There is no SemanticCache any more, and its removal is the interesting part.

The tests it used to have all passed — using hand-made 3-dimensional vectors like
[1.0, 0.0, 0.0] against [0.99, 0.01, 0.0]: cosine ~0.9999, comfortably over the 0.92
threshold. Green ticks all the way down.

Real 1536-dim embeddings behave nothing like that. Measured with the actual model,
genuine paraphrases land at 0.656-0.838 — so the cache never once cleared 0.92 in
production — while meaning-INVERTED pairs reach 0.863 ("anime with a strong female
lead" vs "...strong male lead"). The near-misses outscore the paraphrases, so no
threshold could admit a real hit without sometimes serving the opposite of what was
asked.

The synthetic vectors weren't a harmless shortcut, they were the whole bug: they
encoded a false assumption about embedding geometry and then asserted it. See
anime_core.caches for the full measurement.
"""

from __future__ import annotations

import pytest
from anime_core.cache import InMemoryCache
from anime_core.caches import CORPUS_VERSION, EmbeddingCache, ResponseCache, normalize_query


@pytest.mark.asyncio
async def test_embedding_cache_roundtrip() -> None:
    ec = EmbeddingCache(InMemoryCache())
    assert await ec.get("hello") is None
    await ec.set("hello", [0.1, 0.2, 0.3])
    assert await ec.get("hello") == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_response_cache_roundtrip_and_isolation() -> None:
    rc = ResponseCache(InMemoryCache())
    await rc.set(tenant=None, query="thriller", value={"items": [1]})
    assert await rc.get(tenant=None, query="thriller") == {"items": [1]}
    # different query → miss
    assert await rc.get(tenant=None, query="comedy") is None
    # different tenant → miss (isolation: never serve one user's answer to another)
    assert await rc.get(tenant="user-2", query="thriller") is None


def test_response_cache_key_is_version_scoped() -> None:
    key = ResponseCache._key(None, "thriller")
    assert key.startswith(f"resp:{CORPUS_VERSION}:anon:")


# ── query normalization: the safe half of what the semantic cache attempted ───


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Show me sports anime", "show me sports anime"),  # case
        ("show me sports anime!", "show me sports anime"),  # punctuation
        ("  show me   sports anime ", "show me sports anime"),  # whitespace
        ("Show me SPORTS anime!!!", "show me sports anime"),  # all three
    ],
)
def test_trivial_variants_share_a_cache_key(a: str, b: str) -> None:
    """The realistic near-duplicate: same words, typed differently.

    The key used to be a hash of the RAW query, so "Show me sports anime!" and
    "show me sports anime" were two different keys — the identical request, cached
    twice, hit never.
    """
    assert ResponseCache._key(None, a) == ResponseCache._key(None, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        # THE pair that killed the semantic cache: cosine 0.863, higher than any
        # genuine paraphrase. Normalization isn't fooled, precisely because it does
        # not pretend to understand meaning — different words, different key.
        ("anime with a strong female lead", "anime with a strong male lead"),
        ("romance anime with a happy ending", "romance anime with a sad ending"),
        ("short anime under 12 episodes", "long anime over 100 episodes"),
        ("anime for kids", "anime for adults"),
        # Word order can change the request; a cache is the last place to guess.
        ("anime like death note", "death note like anime"),
    ],
)
def test_different_meanings_never_share_a_cache_key(a: str, b: str) -> None:
    """A hit here would serve the answer to a DIFFERENT question.

    This is the property the cosine-threshold semantic cache could not hold at any
    threshold, and the reason it was deleted rather than retuned. A slow correct
    answer costs two seconds; a fast wrong one costs trust.
    """
    assert ResponseCache._key(None, a) != ResponseCache._key(None, b)


def test_normalization_does_not_change_meaning() -> None:
    """Conservative by design: no stemming, no stopword removal, no reordering."""
    assert normalize_query("Show me SPORTS anime!!!") == "show me sports anime"
    # stopwords survive: "with" vs "without" is a different request
    assert normalize_query("anime with romance") != normalize_query("anime without romance")
    # negation survives — dropping "not" would be catastrophic
    assert normalize_query("anime that is not sad") != normalize_query("anime that is sad")


def test_unicode_variants_normalize_together() -> None:
    """Full-width characters are the same request typed on a different keyboard.

    ruff flags these as "ambiguous unicode" — which is exactly the point. A user on a
    Japanese IME types them without thinking, and NFKC folding is what makes them the
    same cache key instead of a permanent miss.
    """
    assert normalize_query("ＡＮＩＭＥ") == normalize_query("anime")  # noqa: RUF001
