"""End-to-end ingestion test against a live Postgres+pgvector instance.

Requires (skipped otherwise):
    - DATABASE_URL env var pointing at a running, migrated Postgres
    - OPENAI_API_KEY env var
    - data/anime_with_synopsis.csv present

Bring the stack up:
    make db-up && make db-migrate && export OPENAI_API_KEY=sk-...
    uv run pytest tests/integration -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from anime_core.db.engine import session_scope
from anime_core.db.models import AnimeChunk, AnimeTitle
from anime_core.embeddings import OpenAIEmbedder
from anime_ingestion.indexer import ingest
from sqlalchemy import func, select

CORPUS_CSV = Path(__file__).resolve().parents[2] / "data" / "anime_with_synopsis.csv"


# Opt-in only: `uv run pytest -m integration` (also needs the env below).
pytestmark = pytest.mark.integration


def _has_db() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
@pytest.mark.skipif(not _has_openai(), reason="OPENAI_API_KEY not set")
@pytest.mark.skipif(not CORPUS_CSV.exists(), reason=f"corpus CSV missing at {CORPUS_CSV}")
@pytest.mark.asyncio
async def test_ingest_corpus_end_to_end() -> None:
    """Ingest the anime corpus into pgvector and assert table populations."""
    embedder = OpenAIEmbedder()
    async with session_scope() as session:
        stats = await ingest(
            session=session,
            csv_path=CORPUS_CSV,
            embedder=embedder,
            measure_per_query_latency=False,
        )

    assert stats["anime_count"] > 100
    assert stats["chunk_count"] >= stats["anime_count"]

    async with session_scope() as session:
        titles = (await session.execute(select(func.count()).select_from(AnimeTitle))).scalar_one()
        chunks = (await session.execute(select(func.count()).select_from(AnimeChunk))).scalar_one()

    assert titles > 100
    assert chunks >= titles


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
@pytest.mark.skipif(not _has_openai(), reason="OPENAI_API_KEY not set")
@pytest.mark.skipif(not CORPUS_CSV.exists(), reason=f"corpus CSV missing at {CORPUS_CSV}")
@pytest.mark.asyncio
async def test_ingest_is_idempotent() -> None:
    """Running ingest twice yields the same row counts."""
    embedder = OpenAIEmbedder()
    async with session_scope() as session:
        first = await ingest(
            session=session,
            csv_path=CORPUS_CSV,
            embedder=embedder,
            measure_per_query_latency=False,
        )
    async with session_scope() as session:
        second = await ingest(
            session=session,
            csv_path=CORPUS_CSV,
            embedder=embedder,
            measure_per_query_latency=False,
        )
    assert first["anime_count"] == second["anime_count"]
    assert first["chunk_count"] == second["chunk_count"]
