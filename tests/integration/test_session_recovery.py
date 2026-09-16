"""Retrieval must leave the request session usable after a cancelled query (L.16).

Reproduces the production 500 of 2026-09-14 against a real Postgres. A retrieval leg
that outlives its time limit is cancelled mid-query, which invalidates the connection
behind the SHARED request session. Without a rollback, the next statement on that
session raises PendingRollbackError: the sparse fallback fails, then the route's
history write fails, and a designed "degraded, 200" response becomes a 500.

Requires DATABASE_URL pointing at a running Postgres (no migrations or data needed):
    uv run pytest -m integration tests/integration/test_session_recovery.py
"""

from __future__ import annotations

import asyncio
import os

import pytest
from anime_core.db.engine import get_session_factory
from anime_core.embeddings import EmbedResult
from anime_core.vector_index import VectorMatch
from anime_retrieval.hybrid import HybridRetriever
from anime_retrieval.sparse import BM25Match
from sqlalchemy import text
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.ext.asyncio import AsyncSession

# Opt-in only: `uv run pytest -m integration` (also needs DATABASE_URL).
pytestmark = pytest.mark.integration

# Far longer than the timeouts below, so cancellation is guaranteed.
SLOW_QUERY = text("SELECT pg_sleep(5)")


def _has_db() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


class SlowVectorIndex:
    """Dense leg whose query outlives the retriever's timeout, like pgvector did at 2,039 ms."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, embedding, *, k, tenant_id=None) -> list[VectorMatch]:  # type: ignore[no-untyped-def]
        await self._session.execute(SLOW_QUERY)
        return []


class SessionBM25Index:
    """Sparse leg that needs the SAME session to still work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query, *, k, tenant_id=None) -> list[BM25Match]:  # type: ignore[no-untyped-def]
        await self._session.execute(text("SELECT 1"))
        return [BM25Match(mal_id=2, chunk_index=0, text="a2", score=1.0)]


class DummyEmbedder:
    @property
    def model(self) -> str:
        return "d"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
async def test_cancelled_query_leaves_the_session_unusable() -> None:
    """The failure mechanism on its own: a timed-out query poisons the session."""
    session = get_session_factory()()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(session.execute(SLOW_QUERY), timeout=0.2)
        with pytest.raises(PendingRollbackError):
            await session.execute(text("SELECT 1"))
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.skipif(not _has_db(), reason="DATABASE_URL not set")
async def test_retriever_recovers_the_session_after_a_cancelled_leg() -> None:
    """With the recovery hook, the sparse leg AND the route's later statements still work."""
    session = get_session_factory()()
    try:
        retriever = HybridRetriever(
            vector_index=SlowVectorIndex(session),
            bm25_index=SessionBM25Index(session),
            embedder=DummyEmbedder(),
            timeout_seconds=0.2,
            on_leg_failure=session.rollback,
        )
        results = await retriever.retrieve("q", query_embedding=[1.0, 0.0])

        assert [c.mal_id for c in results] == [2]  # sparse ran on the recovered session
        # What repo.ensure_user() does next in the route: must not raise.
        await session.execute(text("SELECT 1"))
    finally:
        await session.rollback()
        await session.close()
