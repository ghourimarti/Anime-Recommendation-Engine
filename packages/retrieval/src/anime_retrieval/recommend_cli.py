"""Recommend CLI — full retrieve → generate → ground flow for one query.

    uv run python -m anime_retrieval.recommend_cli --query "psychological thriller"
    uv run python -m anime_retrieval.recommend_cli --query "..." --stream

Live: needs a migrated + ingested Postgres, OPENAI_API_KEY (query embedding),
and GROQ_API_KEY (generation). First run downloads the reranker weights.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from anime_core.llm_client import build_default_tiered_client
from dotenv import load_dotenv

from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.service import (
    RecommendationService,
    build_context,
    ground_recommendations,
)


def _print_recommendations(query: str, recs) -> None:  # type: ignore[no-untyped-def]
    print(f"\nQuery: {query!r}\n")
    if recs.is_empty:
        print("(no grounded recommendations)")
        return
    for i, r in enumerate(recs.items, start=1):
        print(f"{i}. {r.title}  [mal_id={r.mal_id}]")
        print(f"   {r.summary}")
        print(f"   Why: {r.why_match}\n")


async def _run_debug(query: str, pipeline: RetrievalPipeline, llm) -> int:  # type: ignore[no-untyped-def]
    """Print every stage so we can see exactly where a query goes wrong."""
    candidates = await pipeline.retrieve(query)
    print(f"\n[debug] retrieved {len(candidates)} candidates: {[c.mal_id for c in candidates]}")
    if not candidates:
        print("[debug] retrieval returned nothing — problem is upstream (ingest/retrieve).")
        return 1
    context = build_context(candidates)
    raw = await llm.recommend(query=query, context=context)
    print(
        f"[debug] LLM returned {len(raw.items)} items: {[(r.mal_id, r.title) for r in raw.items]}"
    )
    grounded = ground_recommendations(raw, candidates)
    print(
        f"[debug] after grounding: {len(grounded.items)} items: {[r.mal_id for r in grounded.items]}"
    )
    _print_recommendations(query, grounded)
    return 0 if not grounded.is_empty else 1


async def _amain(query: str, stream: bool, debug: bool) -> int:
    load_dotenv()
    embedder = OpenAIEmbedder()
    llm = build_default_tiered_client()
    async with session_scope() as session:
        pipeline = RetrievalPipeline(session=session, embedder=embedder)
        if debug:
            return await _run_debug(query, pipeline, llm)
        service = RecommendationService(retriever=pipeline, llm=llm)
        if stream:
            print(f"\nQuery: {query!r}\n")
            async for token in service.astream(query):
                sys.stdout.write(token)
                sys.stdout.flush()
            print()
            return 0
        recs = await service.recommend(query)
    _print_recommendations(query, recs)
    return 0 if not recs.is_empty else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grounded anime recommendations.")
    parser.add_argument("--query", "-q", required=True, help="Natural-language preference query.")
    parser.add_argument(
        "--stream", action="store_true", help="Stream tokens instead of structured output."
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print each stage (candidates/raw/grounded)."
    )
    args = parser.parse_args()
    query = args.query.strip()
    if not query:
        parser.error("--query must be a non-empty string")
    sys.exit(asyncio.run(_amain(query, args.stream, args.debug)))


if __name__ == "__main__":
    main()
