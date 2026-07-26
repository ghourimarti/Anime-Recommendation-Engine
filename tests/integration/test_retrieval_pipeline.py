"""End-to-end retrieval pipeline test against a populated pgvector.

Requires (skipped otherwise):
    - DATABASE_URL pointing at a migrated + ingested Postgres
    - OPENAI_API_KEY for query embedding
    - A first-time run downloads ~1.1 GB of `bge-reranker-v2-m3` weights
"""

from __future__ import annotations

import os

import pytest
from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from anime_retrieval.pipeline import RetrievalPipeline

# Opt-in only: `uv run pytest -m integration` (also needs the env below).
pytestmark = pytest.mark.integration


def _has_db() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
@pytest.mark.skipif(not _has_openai(), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_pipeline_returns_three_diverse_anime() -> None:
    """Smoke: pipeline returns up to 3 results with all stage scores populated."""
    embedder = OpenAIEmbedder()
    async with session_scope() as session:
        pipeline = RetrievalPipeline(session=session, embedder=embedder)
        results = await pipeline.retrieve("light hearted school anime")

    assert 1 <= len(results) <= 3
    # All results have a final rank
    assert [c.rank for c in results] == list(range(1, len(results) + 1))
    # No duplicate anime in the top-3 (the dedup_by_anime invariant)
    assert len({c.mal_id for c in results}) == len(results)
    # Every result has all pipeline-stage scores
    for c in results:
        assert c.hybrid_score is not None
        assert c.rerank_score is not None
        assert c.mmr_score is not None
