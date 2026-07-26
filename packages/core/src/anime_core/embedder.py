"""Embedder Protocol + caching decorator.

The `Embedder` Protocol is the seam that lets retrieval/ingestion depend on a
contract, not the concrete OpenAI client — so `CachingEmbedder` (and a future
local embedder) can be dropped in anywhere. `OpenAIEmbedder` satisfies this
structurally without inheriting.

Kept separate from embeddings.py (the OpenAI client) so the client stays focused
and the caching concern is isolated.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from anime_core.caches import EmbeddingCache
from anime_core.embeddings import EmbedResult


class Embedder(Protocol):
    """Anything that turns texts into vectors. OpenAIEmbedder + CachingEmbedder satisfy it."""

    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> EmbedResult: ...


class CachingEmbedder:
    """Wraps an Embedder with a per-text embedding cache.

    Per-text (not per-batch) caching: a batch with some cached and some new texts
    only sends the misses to the inner embedder, so partial-hit batches still save
    API calls. Returns embeddings in the original input order.
    """

    def __init__(self, *, inner: Embedder, cache: EmbeddingCache) -> None:
        self._inner = inner
        self._cache = cache

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def dim(self) -> int:
        return self._inner.dim

    async def embed(self, texts: Sequence[str]) -> EmbedResult:
        text_list = list(texts)
        cached: list[list[float] | None] = [await self._cache.get(t) for t in text_list]
        miss_indices = [i for i, value in enumerate(cached) if value is None]

        total_tokens = 0
        latency_seconds = 0.0
        if miss_indices:
            miss_texts = [text_list[i] for i in miss_indices]
            result = await self._inner.embed(miss_texts)
            total_tokens = result.total_tokens
            latency_seconds = result.latency_seconds
            for idx, embedding in zip(miss_indices, result.embeddings, strict=True):
                cached[idx] = embedding
                await self._cache.set(text_list[idx], embedding)

        embeddings = [value for value in cached if value is not None]
        return EmbedResult(
            embeddings=embeddings,
            total_tokens=total_tokens,
            latency_seconds=latency_seconds,
        )
