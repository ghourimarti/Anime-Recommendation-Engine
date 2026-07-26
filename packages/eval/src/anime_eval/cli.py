"""Eval CLI — runs the advanced pipeline vs the naive baseline over the golden
set and prints a comparison. This is the A/B that proves the reranker lift and, by
swapping the embedding model in .env, answers the embedding-model question.

    uv run python -m anime_eval.cli                 # advanced vs naive, IR metrics
    uv run python -m anime_eval.cli --ragas         # also run RAGAS (needs extra+key)
    uv run python -m anime_eval.cli --json out.json # write machine-readable report

Live: needs a migrated + ingested Postgres and OPENAI_API_KEY (query embedding).
First run also downloads the reranker weights (~1.1 GB).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from anime_core.console import use_utf8_stdout
from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.reranker import BgeReranker
from dotenv import load_dotenv

from anime_eval.baseline import NaiveRetriever
from anime_eval.golden import load_golden_set
from anime_eval.runner import EvalReport, compare, run_eval


def _print_comparison(naive: EvalReport, advanced: EvalReport) -> None:
    table = compare(naive, advanced)
    print(f"\n{'metric':<16} {'naive':>10} {'advanced':>10} {'delta':>10}")
    print("-" * 50)
    for name, row in table.items():
        arrow = "↑" if row["delta"] > 0.0001 else ("↓" if row["delta"] < -0.0001 else " ")
        print(
            f"{name:<16} {row['baseline']:>10.3f} {row['candidate']:>10.3f} "
            f"{row['delta']:>+9.3f}{arrow}"
        )
    print(
        f"\nScored queries: {len(advanced.per_query)}  |  "
        f"Adversarial (informational): {len(advanced.adversarial)}"
    )


async def _amain(emit_json: Path | None, run_ragas: bool) -> int:
    golden = load_golden_set()
    embedder = OpenAIEmbedder()

    # Warm the cross-encoder BEFORE scoring. A cold load costs ~2s — about the
    # whole RERANK_TIMEOUT — so an un-warmed run times out on its first queries,
    # silently falls back to hybrid order, and under-reports the reranker's lift.
    # The API warms in lifespan before readiness; eval must match, or it measures
    # a pipeline production never runs.
    reranker = BgeReranker()
    await asyncio.to_thread(reranker.warm)

    async with session_scope() as session:
        naive = await run_eval(
            NaiveRetriever(session=session, embedder=embedder),
            golden,
            retriever_name="naive (dense-only)",
        )
        advanced = await run_eval(
            RetrievalPipeline(session=session, embedder=embedder, reranker=reranker),
            golden,
            retriever_name="advanced (hybrid+rerank+mmr)",
        )

    _print_comparison(naive, advanced)

    ragas_section: dict[str, float] | None = None
    if run_ragas:
        from anime_eval.ragas_runner import run_ragas_eval

        async with session_scope() as session:
            r = await run_ragas_eval(RetrievalPipeline(session=session, embedder=embedder), golden)
        ragas_section = {
            "context_precision": r.context_precision,
            "context_recall": r.context_recall,
        }
        print(
            f"\nRAGAS (advanced):  context_precision={r.context_precision:.3f}  "
            f"context_recall={r.context_recall:.3f}  (n={r.n_queries})"
        )

    if emit_json is not None:
        payload = {
            "embedding_model": embedder.model,
            "naive": naive.aggregates,
            "advanced": advanced.aggregates,
            "comparison": compare(naive, advanced),
            "ragas": ragas_section,
        }
        emit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote machine-readable report to {emit_json}")

    return 0


def main() -> None:
    use_utf8_stdout()  # Windows cp1252 cannot encode the '↑' in the delta column
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run anime retrieval eval (advanced vs naive).")
    parser.add_argument("--ragas", action="store_true", help="Also run RAGAS (needs extra + key).")
    parser.add_argument("--json", type=Path, default=None, help="Write a JSON report to this path.")
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args.json, args.ragas)))


if __name__ == "__main__":
    main()
