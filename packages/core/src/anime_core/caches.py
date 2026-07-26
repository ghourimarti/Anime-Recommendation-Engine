"""Typed caches built on the Cache primitive.

Two caches, two jobs:
  - EmbeddingCache: text -> vector. No TTL (a text's embedding is stable). Saves
    the OpenAI round-trip — a latency lever, not just cost, since the embedding-model revision.
  - ResponseCache:  normalized query -> answer. 24h TTL. The cheapest hit.

Keys are prefixed with CORPUS_VERSION so a re-ingest (which changes embeddings and
therefore answers) invalidates the response cache atomically — bump the version,
old keys are orphaned. Tenant is in the key so multi-tenancy never leaks one
user's answer to another.

─── Why there is no SemanticCache ───────────────────────────────────────────────
There used to be one: near-duplicate query -> answer, on cosine >= 0.92 over a
recent-N window. It was billed as "the biggest single cost lever". It never fired
once, and it could not have been made to fire safely. Measured with the real
embedder (text-embedding-3-small) on labelled query pairs:

    paraphrases      (SHOULD hit)   cosine 0.656 .. 0.838
    meaning-inverted (MUST NOT hit) cosine 0.470 .. 0.863

    "anime with a strong female lead" vs "...strong male lead"     -> 0.863
    "romance anime with a happy ending" vs "...with a sad ending"  -> 0.842
    (best genuine paraphrase, for comparison)                      -> 0.838

The near-misses score HIGHER than the paraphrases. There is no threshold that
admits a single paraphrase without also admitting "male lead" as an answer to
"female lead". At 0.92 the cache simply never hit — safe, and useless. Lowering it
to "fix" the hit rate would have started serving wrong answers, which is strictly
worse than a miss: a slow correct answer costs 2 seconds, a fast wrong one costs
trust.

Retrieval overlap doesn't rescue it either (paraphrases overlap@10 as low as 0.40;
the female/male-lead pair overlaps 0.50). Embeddings encode topical similarity,
not logical polarity — "happy ending" and "sad ending" are topically near-identical
— so no threshold over this signal separates them.

So the cache is gone, and the response cache now normalizes its key instead, which
catches the realistic near-duplicate ("Show me sports anime!" vs "show me sports
anime") deterministically and cannot ever return someone else's answer.

If a semantic cache is ever wanted back, it needs an equivalence check embeddings
cannot provide — e.g. a cheap LLM judge on the candidate pair (~$0.000004, ~300ms,
against ~$0.0004 and ~2.5s for the generation it would save). That is a real
design; cosine alone is not.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from typing import Any

from anime_core.cache import Cache

CORPUS_VERSION = os.environ.get("CORPUS_VERSION", "v1")
RESPONSE_TTL_SECONDS = 86_400  # 24h

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Canonicalize a query so trivially-different spellings share a cache key.

    Deliberately conservative: case, surrounding/duplicated whitespace, punctuation
    and Unicode form. Nothing that could change MEANING. It does not stem, drop
    stopwords, or reorder words — "anime like death note" and "death note like
    anime" stay distinct, because they are not reliably the same request, and a
    cache is the last place to be clever.

    This is the safe half of what the semantic cache was trying to do. The unsafe
    half — deciding that two *differently worded* queries mean the same thing — is
    what no cosine threshold could do correctly (see the module docstring).
    """
    text = unicodedata.normalize("NFKC", query).casefold().strip()
    text = _PUNCT.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """text -> embedding vector. No TTL."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def get(self, text: str) -> list[float] | None:
        raw = await self._cache.get(f"embed:{_hash(text)}")
        if raw is None:
            return None
        return [float(x) for x in json.loads(raw)]

    async def set(self, text: str, embedding: list[float]) -> None:
        await self._cache.set(f"embed:{_hash(text)}", json.dumps(embedding))


class ResponseCache:
    """normalized query -> answer payload. 24h TTL, version- and tenant-scoped."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    @staticmethod
    def _key(tenant: str | None, query: str) -> str:
        # Hash the NORMALIZED query. Hashing the raw string made
        # "Show me sports anime!" and "show me sports anime" two different keys —
        # the same request, cached twice, hit never.
        return f"resp:{CORPUS_VERSION}:{tenant or 'anon'}:{_hash(normalize_query(query))}"

    async def get(self, *, tenant: str | None, query: str) -> dict[str, Any] | None:
        raw = await self._cache.get(self._key(tenant, query))
        return json.loads(raw) if raw is not None else None

    async def set(self, *, tenant: str | None, query: str, value: dict[str, Any]) -> None:
        await self._cache.set(
            self._key(tenant, query), json.dumps(value), ttl_seconds=RESPONSE_TTL_SECONDS
        )
