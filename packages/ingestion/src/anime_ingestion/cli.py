"""Anime corpus ingestion CLI.

    uv run python -m anime_ingestion.cli --csv data/anime_with_synopsis.csv

Embedding-latency gate: per-query embedding p50 must be < 200 ms (pass),
< 300 ms (warn), otherwise FAIL (exit code 2) — a regression here inflates
ingestion cost and query latency, so we catch it at the source.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from dotenv import load_dotenv

from anime_ingestion.indexer import ingest


async def _amain(csv_path: Path, skip_latency: bool) -> int:
    embedder = OpenAIEmbedder()
    async with session_scope() as session:
        stats = await ingest(
            session=session,
            csv_path=csv_path,
            embedder=embedder,
            measure_per_query_latency=not skip_latency,
        )

    print(json.dumps(stats, indent=2, default=str))

    p50 = stats.get("per_query_latency_p50_seconds")
    if p50 is None:
        return 0
    p50_ms = p50 * 1000
    if p50 < 0.2:
        print(
            f"\nPASS — per-query embedding p50 {p50_ms:.1f} ms < 200 ms target.",
            file=sys.stderr,
        )
        return 0
    if p50 < 0.3:
        print(
            f"\nWARN — per-query embedding p50 {p50_ms:.1f} ms within 200-300 ms tolerance.",
            file=sys.stderr,
        )
        return 0
    print(
        f"\nFAIL — per-query embedding p50 {p50_ms:.1f} ms exceeds 300 ms gate; "
        "revisit the embedding-model choice before proceeding.",
        file=sys.stderr,
    )
    return 2


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Ingest the anime corpus into pgvector.")
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the anime CSV (e.g. data/anime_with_synopsis.csv).",
    )
    parser.add_argument(
        "--skip-latency",
        action="store_true",
        help="Skip the per-query latency measurement (faster reruns).",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(_amain(args.csv, args.skip_latency)))


if __name__ == "__main__":
    main()
