"""Indexer: load CSV → chunk → embed → upsert into pgvector.

Idempotent: re-running on the same CSV produces the same row counts.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

from anime_core.db.models import AnimeChunk as ORMChunk
from anime_core.db.models import AnimeTitle
from anime_core.embedder import Embedder
from anime_core.models import AnimeChunk
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from anime_ingestion.chunker import chunk_anime
from anime_ingestion.loader import load_anime_csv

# Synthetic user-query shapes used to measure single-query embedding latency.
# The latency gate is computed from p50 of these calls.
_LATENCY_PROBE_QUERIES: tuple[str, ...] = (
    "light hearted school anime",
    "psychological thriller with a twist",
    "samurai action with humor",
    "slice of life cooking show",
    "isekai with overpowered protagonist",
    "romance high school drama",
    "mecha post-apocalyptic survival",
    "sports underdog story",
    "supernatural mystery investigation",
    "comedy with strong female lead",
)


async def ingest(
    *,
    session: AsyncSession,
    csv_path: Path | str,
    embedder: Embedder,
    measure_per_query_latency: bool = True,
) -> dict[str, Any]:
    """Run the full ingestion pipeline. Returns a stats dict.

    Stats include:
      - anime_count / chunk_count
      - embed_total_tokens / embed_total_seconds (batch corpus embed)
      - per_query_latency_p50_seconds / per_query_latency_p95_seconds
        (single-query embed latency — the embedding-latency gate)
    """
    animes = load_anime_csv(csv_path)
    chunks: list[AnimeChunk] = []
    for a in animes:
        chunks.extend(chunk_anime(a))

    # Batch-embed all chunks.
    embed_result = await embedder.embed([c.text for c in chunks])
    if len(embed_result.embeddings) != len(chunks):
        raise RuntimeError(
            f"Embedding count {len(embed_result.embeddings)} != chunk count {len(chunks)}"
        )

    # Measure per-query latency (the NFR gate). Sequential, single-query calls.
    per_query_latencies: list[float] = []
    if measure_per_query_latency:
        for q in _LATENCY_PROBE_QUERIES:
            t0 = time.perf_counter()
            await embedder.embed([q])
            per_query_latencies.append(time.perf_counter() - t0)

    # Upsert anime_titles.
    for a in animes:
        stmt = pg_insert(AnimeTitle).values(
            mal_id=a.mal_id,
            name=a.name,
            score=a.score,
            genres=a.genres,
            synopsis=a.synopsis,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["mal_id"],
            set_={
                "name": a.name,
                "score": a.score,
                "genres": a.genres,
                "synopsis": a.synopsis,
            },
        )
        await session.execute(stmt)

    # Idempotent chunk rebuild: delete + insert for the mal_ids in this run.
    mal_ids = sorted({c.mal_id for c in chunks})
    await session.execute(delete(ORMChunk).where(ORMChunk.mal_id.in_(mal_ids)))

    for chunk, embedding in zip(chunks, embed_result.embeddings, strict=True):
        await session.execute(
            pg_insert(ORMChunk).values(
                mal_id=chunk.mal_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=embedding,
                embedding_model=embedder.model,
                chunk_metadata=chunk.metadata,
            )
        )

    p50 = statistics.median(per_query_latencies) if per_query_latencies else None
    p95: float | None
    if len(per_query_latencies) >= 5:
        p95 = statistics.quantiles(per_query_latencies, n=20)[18]
    else:
        p95 = None

    return {
        "anime_count": len(animes),
        "chunk_count": len(chunks),
        "embed_total_tokens": embed_result.total_tokens,
        "embed_total_seconds": embed_result.latency_seconds,
        "per_query_latency_p50_seconds": p50,
        "per_query_latency_p95_seconds": p95,
    }
