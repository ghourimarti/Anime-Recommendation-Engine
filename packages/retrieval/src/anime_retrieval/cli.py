"""Retrieval CLI — runs the full pipeline for a single query, prints stage scores.

uv run python -m anime_retrieval.cli --query "light hearted school anime"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from dotenv import load_dotenv

from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.types import Candidate


def _extract_title(text: str) -> str:
    """Pull the 'Title: ...' header line written by the chunker."""
    if text.startswith("Title: "):
        first_line = text.split("\n", 1)[0]
        return first_line[len("Title: ") :]
    return "<unknown>"


def _format_score(value: float | None) -> str:
    return f"{value:+.4f}" if value is not None else "  -   "


def _print_results(query: str, results: list[Candidate], elapsed_seconds: float) -> None:
    print(f"\nQuery:  {query!r}")
    print(
        f"Total:  {elapsed_seconds * 1000:.0f} ms (incl. embedding + reranker model load if cold)\n"
    )
    if not results:
        print("(no results)")
        return
    print(f"  {'rank':<4}  {'mal_id':>7}  {'hybrid':>9}  {'rerank':>9}  {'mmr':>9}   title")
    print("  " + "-" * 76)
    for c in results:
        title = _extract_title(c.text)
        print(
            f"  #{c.rank:<3}  {c.mal_id:>7}  "
            f"{_format_score(c.hybrid_score):>9}  "
            f"{_format_score(c.rerank_score):>9}  "
            f"{_format_score(c.mmr_score):>9}   "
            f"{title}"
        )


async def _amain(query: str) -> int:
    embedder = OpenAIEmbedder()
    async with session_scope() as session:
        pipeline = RetrievalPipeline(session=session, embedder=embedder)
        t0 = time.perf_counter()
        results = await pipeline.retrieve(query)
        elapsed = time.perf_counter() - t0
    _print_results(query, results, elapsed)
    return 0 if results else 1


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Retrieve the top-3 anime recommendation set.")
    parser.add_argument("--query", "-q", required=True, help="Natural-language preference query.")
    args = parser.parse_args()
    query = args.query.strip()
    if not query:
        parser.error("--query must be a non-empty string (did you forget QUERY=... in make?)")
    sys.exit(asyncio.run(_amain(query)))


if __name__ == "__main__":
    main()
