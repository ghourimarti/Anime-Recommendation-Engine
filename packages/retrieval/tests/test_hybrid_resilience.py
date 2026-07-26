"""Tests for HybridRetriever resilience — dense→sparse fallback, both-down → raise."""

from __future__ import annotations

import pytest
from anime_core.resilience import RetrievalUnavailableError
from anime_core.vector_index import VectorMatch
from anime_retrieval.hybrid import HybridRetriever
from anime_retrieval.sparse import BM25Match


class OkVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [VectorMatch(mal_id=1, chunk_index=0, text="a1", score=0.9)]


class DownVector:
    async def search(self, embedding, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("pgvector down")


class OkBM25:
    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        return [BM25Match(mal_id=2, chunk_index=0, text="a2", score=1.0)]


class DownBM25:
    async def search(self, query, *, k, tenant_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("FTS down")


class DummyEmbedder:
    @property
    def model(self) -> str:
        return "d"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        from anime_core.embeddings import EmbedResult

        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


def _retriever(vector, bm25) -> HybridRetriever:  # type: ignore[no-untyped-def]
    return HybridRetriever(vector_index=vector, bm25_index=bm25, embedder=DummyEmbedder())


@pytest.mark.asyncio
async def test_dense_down_falls_back_to_sparse_only() -> None:
    r = _retriever(DownVector(), OkBM25())
    results = await r.retrieve("q", query_embedding=[1.0, 0.0])
    assert [c.mal_id for c in results] == [2]  # sparse-only result


@pytest.mark.asyncio
async def test_sparse_down_uses_dense_only() -> None:
    r = _retriever(OkVector(), DownBM25())
    results = await r.retrieve("q", query_embedding=[1.0, 0.0])
    assert [c.mal_id for c in results] == [1]


@pytest.mark.asyncio
async def test_both_down_raises_retrieval_unavailable() -> None:
    r = _retriever(DownVector(), DownBM25())
    with pytest.raises(RetrievalUnavailableError):
        await r.retrieve("q", query_embedding=[1.0, 0.0])
