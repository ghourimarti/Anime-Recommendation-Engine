"""Tests for CachingEmbedder — a cache hit must skip the inner (OpenAI) call."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from anime_core.cache import InMemoryCache
from anime_core.caches import EmbeddingCache
from anime_core.embedder import CachingEmbedder
from anime_core.embeddings import EmbedResult


class SpyEmbedder:
    """Counts how many texts it was asked to embed; returns deterministic vectors."""

    def __init__(self) -> None:
        self.embedded_texts: list[str] = []

    @property
    def model(self) -> str:
        return "spy"

    @property
    def dim(self) -> int:
        return 3

    async def embed(self, texts: Sequence[str]) -> EmbedResult:
        text_list = list(texts)
        self.embedded_texts.extend(text_list)
        return EmbedResult(
            embeddings=[[float(len(t)), 0.0, 0.0] for t in text_list],
            total_tokens=len(text_list),
            latency_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_repeat_embed_skips_inner() -> None:
    spy = SpyEmbedder()
    emb = CachingEmbedder(inner=spy, cache=EmbeddingCache(InMemoryCache()))

    first = await emb.embed(["light hearted school anime"])
    assert spy.embedded_texts == ["light hearted school anime"]

    second = await emb.embed(["light hearted school anime"])
    # inner NOT called again — still just the one text
    assert spy.embedded_texts == ["light hearted school anime"]
    assert first.embeddings == second.embeddings


@pytest.mark.asyncio
async def test_partial_batch_only_embeds_misses() -> None:
    spy = SpyEmbedder()
    emb = CachingEmbedder(inner=spy, cache=EmbeddingCache(InMemoryCache()))

    await emb.embed(["a"])  # warm "a"
    spy.embedded_texts.clear()

    result = await emb.embed(["a", "bb", "ccc"])  # only "bb","ccc" are misses
    assert spy.embedded_texts == ["bb", "ccc"]
    # order preserved, all three returned
    assert result.embeddings == [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]


@pytest.mark.asyncio
async def test_model_and_dim_delegate() -> None:
    emb = CachingEmbedder(inner=SpyEmbedder(), cache=EmbeddingCache(InMemoryCache()))
    assert emb.model == "spy"
    assert emb.dim == 3
