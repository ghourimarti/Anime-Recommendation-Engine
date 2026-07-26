"""BM25-style sparse retrieval via Postgres full-text search.

The `text_tsv` GENERATED column (added in migration 0001_initial) holds the
pre-computed tsvector. We rank with `ts_rank_cd` (cover-density), which weights
query-term proximity — appropriate for natural-language preference queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class BM25Match:
    """A retrieval hit from the BM25/FTS index."""

    mal_id: int
    chunk_index: int
    text: str
    score: float  # ts_rank_cd — unbounded, higher = more relevant


class BM25Index(Protocol):
    """The swap-point for sparse retrieval (Postgres FTS today; OpenSearch later)."""

    async def search(
        self,
        query: str,
        *,
        k: int,
        tenant_id: str | None = None,
    ) -> list[BM25Match]: ...


class PostgresBM25Index:
    """Postgres FTS implementation. Uses `plainto_tsquery` to safely parse user input."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        query: str,
        *,
        k: int,
        tenant_id: str | None = None,  # unused v1; pattern preserved for ACL parity
    ) -> list[BM25Match]:
        sql = text(
            """
            SELECT
                mal_id,
                chunk_index,
                text,
                ts_rank_cd(text_tsv, q) AS rank
            FROM anime_chunks, plainto_tsquery('english', :query) AS q
            WHERE text_tsv @@ q
            ORDER BY rank DESC
            LIMIT :k
            """
        )
        result = await self._session.execute(sql, {"query": query, "k": k})
        return [
            BM25Match(
                mal_id=int(row.mal_id),
                chunk_index=int(row.chunk_index),
                text=str(row.text),
                score=float(row.rank),
            )
            for row in result
        ]
