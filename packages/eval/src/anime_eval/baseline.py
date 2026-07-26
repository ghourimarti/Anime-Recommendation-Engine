"""Naive baseline retriever — the A/B foil that isolates the retrieval gains.

Dense-only vector search: no sparse/BM25, no cross-encoder rerank, no MMR. We
retrieve a wider dense pool then dedup to distinct anime so the comparison
against the advanced pipeline is apples-to-apples (both return distinct-anime
top-3). The measured delta is therefore the combined contribution of
hybrid + reranker + MMR.
"""

from __future__ import annotations

import dataclasses

from anime_core.embedder import Embedder
from anime_core.vector_index import PgvectorIndex
from anime_retrieval.types import Candidate
from sqlalchemy.ext.asyncio import AsyncSession


class NaiveRetriever:
    """Dense-only retrieval → dedup by anime → top-k. Satisfies QueryRetriever."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        embedder: Embedder,
        pool: int = 20,
        final_k: int = 3,
    ) -> None:
        self._index = PgvectorIndex(session)
        self._embedder = embedder
        self._pool = pool
        self._final_k = final_k

    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]:
        embedding = (await self._embedder.embed([query])).embeddings[0]
        matches = await self._index.search(embedding, k=self._pool, tenant_id=tenant_id)

        seen: set[int] = set()
        out: list[Candidate] = []
        for m in matches:
            if m.mal_id in seen:
                continue
            seen.add(m.mal_id)
            out.append(
                Candidate(
                    mal_id=m.mal_id,
                    chunk_index=m.chunk_index,
                    text=m.text,
                    dense_score=m.score,
                    rank=len(out) + 1,
                )
            )
            if len(out) >= self._final_k:
                break
        return [dataclasses.replace(c, rank=i + 1) for i, c in enumerate(out)]
