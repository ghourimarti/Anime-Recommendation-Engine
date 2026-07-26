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
