"""VectorIndex Protocol + pgvector implementation.

This is the swap-point boundary for the "pgvector now, Qdrant later"
plan. The Protocol is the contract — any future backend (Qdrant, Pinecone) must
implement it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anime_core.db.models import EMBEDDING_DIM
from anime_core.db.models import AnimeChunk as ORMChunk


@dataclass(frozen=True)
class VectorMatch:
    """A retrieval hit from the vector index."""

    mal_id: int
    chunk_index: int
    text: str
    score: float  # cosine similarity in [0, 1] — higher = more similar


class VectorIndex(Protocol):
    """The swap-point boundary for vector storage."""

    async def search(
        self,
        embedding: list[float],
        *,
        k: int,
        tenant_id: str | None = None,
    ) -> list[VectorMatch]:
        """Return the top-k nearest chunks by cosine similarity.

        `tenant_id` is reserved for the multi-tenant ACL filter (populated once auth is on).
        For v1 (anime is public content) it is unused, but the parameter is
        always present so the discipline is enforced at the interface boundary.
        """
        ...


class PgvectorIndex:
    """pgvector-backed implementation of VectorIndex."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def warm(self) -> None:
        """Run one throwaway nearest-neighbour query so the first REAL one is not the first.

        Measured on this stack: dense retrieval times out on the first ~2 requests after
        `make up` and then answers the same query in 54ms. The cost is first-use work --
        connection, plan, and pgvector's index pages -- and it lands on whoever queries
        first. Because retrieval degrades on purpose, that user silently gets sparse-only
        results and a 200, so the symptom is invisible unless you are watching the stage
        metrics. Any battery that starts measuring at request #1 reads a healthy stack as
        broken (the reason the inspection script warms up first).

        Deliberately NOT a zero vector: cosine distance against zero is undefined and
        pgvector yields NaN, which sorts unpredictably and would exercise a different
        path from the real one. A unit vector is a legitimate point in the space.

        Costs no OpenAI call -- the embedding is synthetic, and only the query path is
        being warmed, not the embedder.
        """
        await self.search([1.0] + [0.0] * (EMBEDDING_DIM - 1), k=1)

    async def search(
        self,
        embedding: list[float],
        *,
        k: int,
        tenant_id: str | None = None,
    ) -> list[VectorMatch]:
        # pgvector cosine-distance operator <=> returns 1 - cosine_similarity,
        # so we invert to get similarity in [0, 1].
        distance = ORMChunk.embedding.cosine_distance(embedding)
        stmt = (
            select(
                ORMChunk.mal_id,
                ORMChunk.chunk_index,
                ORMChunk.text,
                (1.0 - distance).label("score"),
            )
            .order_by(distance)
            .limit(k)
        )
        result = await self._session.execute(stmt)
        return [
            VectorMatch(
                mal_id=int(row.mal_id),
                chunk_index=int(row.chunk_index),
                text=str(row.text),
                score=float(row.score),
            )
            for row in result
        ]
