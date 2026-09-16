"""RetrievalPipeline must wire session recovery into its hybrid retriever (L.16).

No database: the fake session breaks its transaction when a statement fails, the way
an AsyncSession does after a cancelled or failed query. Real-Postgres proof of that
behaviour: tests/integration/test_session_recovery.py
"""

from __future__ import annotations

import pytest
from anime_core.embeddings import EmbedResult
from anime_retrieval.pipeline import RetrievalPipeline
from sqlalchemy.exc import OperationalError, PendingRollbackError


class BreakingSession:
    """First statement (the dense pgvector query) fails and poisons the transaction."""

    def __init__(self, *, fail_first: bool = True) -> None:
        self._fail_first = fail_first
        self.broken = False
        self.statements = 0
        self.rollbacks = 0

    async def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.statements += 1
        if self.broken:
            raise PendingRollbackError("Can't reconnect until invalid transaction is rolled back")
        if self._fail_first and self.statements == 1:
            self.broken = True
            raise OperationalError("SELECT ...", {}, Exception("canceling statement"))
        return []  # no rows

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.broken = False


class DummyEmbedder:
    @property
    def model(self) -> str:
        return "d"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


class NoReranker:
    def score(self, query, texts):  # type: ignore[no-untyped-def]
        return [0.0] * len(texts)


def _pipeline(session: BreakingSession) -> RetrievalPipeline:
    return RetrievalPipeline(
        session=session,  # type: ignore[arg-type]
        embedder=DummyEmbedder(),
        reranker=NoReranker(),
    )


@pytest.mark.asyncio
async def test_failed_dense_query_is_rolled_back_so_sparse_still_runs() -> None:
    session = BreakingSession()
    # Without the wiring, sparse hits PendingRollbackError, both legs fail and this
    # raises RetrievalUnavailableError: the request degrades, then its history write
    # on the same session fails with a 500.
    assert await _pipeline(session).retrieve("q") == []
    assert session.rollbacks == 1
    assert session.statements == 2  # dense failed, sparse ran
    assert not session.broken  # the route's later writes can use the session


@pytest.mark.asyncio
async def test_healthy_retrieval_does_not_roll_back() -> None:
    session = BreakingSession(fail_first=False)
    assert await _pipeline(session).retrieve("q") == []
    assert session.rollbacks == 0
