"""CLI: run the refusal eval against the real service (retrieval + LLM).

    uv run python -m anime_eval.refusal_cli          # or: make eval-refusal

Costs one LLM call per query, so it is deliberately not part of `make eval`.
Exits non-zero if the model fails the refusal thresholds — this is a gate, not a
report: shipping a recommender that answers "what is the capital of France" with
three anime is a correctness bug, not a curiosity.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from anime_core.cache import get_cache
from anime_core.caches import EmbeddingCache
from anime_core.console import use_utf8_stdout
from anime_core.db.engine import session_scope
from anime_core.embedder import CachingEmbedder
from anime_core.embeddings import OpenAIEmbedder
from anime_core.llm_client import build_default_llm_client
from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.reranker import BgeReranker
from anime_retrieval.service import RecommendationService
from dotenv import load_dotenv

from anime_eval.golden import load_golden_set
from anime_eval.refusal import render_refusal, run_refusal_eval

# An out-of-scope query answered with three anime is a confident lie, so the bar for
# honesty is high. The false-refusal bar is strict too: "refuse everything" is not a
# fix, it is a different failure.
MIN_REFUSAL_RECALL = 0.80
MAX_FALSE_REFUSAL_RATE = 0.20


async def _amain(min_recall: float, max_false: float) -> int:
    load_dotenv()
    golden = load_golden_set()

    cache = get_cache()
    embedder = CachingEmbedder(inner=OpenAIEmbedder(), cache=EmbeddingCache(cache))
    reranker = BgeReranker()
    await asyncio.to_thread(reranker.warm)  # never measure a cold pipeline

    async with session_scope() as session:
        pipeline = RetrievalPipeline(session=session, embedder=embedder, reranker=reranker)
        service = RecommendationService(retriever=pipeline, llm=build_default_llm_client())
        report = await run_refusal_eval(service, golden)

    sys.stdout.write(render_refusal(report))

    failures = []
    if report.refusal_recall < min_recall:
        failures.append(
            f"refusal_recall {report.refusal_recall:.2f} < {min_recall:.2f} — the model is "
            f"answering questions it cannot answer (confabulation)"
        )
    if report.false_refusal_rate > max_false:
        failures.append(
            f"false_refusal_rate {report.false_refusal_rate:.2f} > {max_false:.2f} — the model "
            f"is refusing questions it CAN answer (over-refusal is not a fix)"
        )

    if failures:
        print("\nREFUSAL GATE FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\nREFUSAL GATE PASSED")
    return 0


def main() -> None:
    use_utf8_stdout()  # model refusals contain typographic quotes (U+2019)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min-refusal-recall", type=float, default=MIN_REFUSAL_RECALL)
    p.add_argument("--max-false-refusal-rate", type=float, default=MAX_FALSE_REFUSAL_RATE)
    args = p.parse_args()
    sys.exit(asyncio.run(_amain(args.min_refusal_recall, args.max_false_refusal_rate)))


if __name__ == "__main__":
    main()
