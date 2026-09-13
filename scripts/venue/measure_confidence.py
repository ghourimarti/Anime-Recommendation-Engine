#!/usr/bin/env python3
"""Characterise the rerank-score distribution over the golden set (S21.4a).

WHY THIS SCRIPT EXISTS
----------------------
Decision gate G2 chose retrieval-confidence routing over a word-count
heuristic. `llm_client.default_should_escalate` already warned about exactly
this:

    "A confidence-based trigger (retrieval rerank score) is a v2 refinement
     once we characterize the score distribution - we don't invent a threshold
     on a distribution we haven't measured."

So this runs the 111 golden queries through the real retrieval pipeline,
records the rerank score of the top candidate, and groups by the golden set's
own `query_type` label (clear / edge / vague / adversarial).

THE HYPOTHESIS BEING TESTED
---------------------------
Routing to a 7B venue is safe when retrieval is confident: if the reranker
found a strong match, the context is good and a small model can summarise it.
If retrieval is uncertain, the query needs the stronger hosted model.

That predicts: clear > edge > vague in top-1 rerank score.

THIS SCRIPT CAN REFUTE G2. If the query types do not separate, then rerank
score is not a usable routing signal on this corpus, and the honest outcome is
to report that and fall back to G2 option A - not to pick a threshold anyway.

Cost: ~111 OpenAI embedding calls (~$0.0001). Requires the data tier up
(`make db`) with the corpus ingested.

Usage:
    uv run python scripts/venue/measure_confidence.py
    uv run python scripts/venue/measure_confidence.py --limit 20   # smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from anime_retrieval.pipeline import RetrievalPipeline
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "packages" / "eval" / "src" / "anime_eval" / "golden_sets" / "v1.jsonl"
OUT_DIR = REPO_ROOT / "Documents" / "docs" / "venue-bench"

# Order matters for reading the report: expected confidence, high to low.
TYPE_ORDER = ["clear", "edge", "vague", "adversarial"]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered)) - 1))
    return ordered[idx]


def load_golden(limit: int | None) -> list[dict]:
    rows = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows[:limit] if limit else rows


async def measure(rows: list[dict], *, rerank_timeout: float) -> list[dict]:
    embedder = OpenAIEmbedder()
    out: list[dict] = []
    async with session_scope() as session:
        # Generous rerank timeout, deliberately NOT the production 2.0s.
        #
        # We are measuring the SCORE DISTRIBUTION, not latency. With the prod
        # timeout the cross-encoder's lazy weight-load blows the budget on the
        # first call, the pipeline degrades to hybrid order (rerank_score=None),
        # and every cancelled wait_for leaves an orphaned scoring thread that
        # contends for CPU - so the failures cascade and we would measure
        # nothing at all. Production keeps 2.0s; this is measurement scaffolding.
        pipeline = RetrievalPipeline(session=session, embedder=embedder, rerank_timeout=rerank_timeout)

        # Warm the reranker so query #1 is not paying model-load cost.
        print("  warming reranker (loading cross-encoder weights)...")
        try:
            await pipeline.retrieve("warmup query for reranker model load")
            print("  warm.\n")
        except Exception as exc:
            print(f"  warmup failed: {type(exc).__name__}: {exc}\n")

        for i, row in enumerate(rows, 1):
            query = row["query"]
            try:
                candidates = await pipeline.retrieve(query)
            except Exception as exc:  # a failed query is data, not a crash
                print(f"  [{i:>3}/{len(rows)}] FAILED {row['id']}: {type(exc).__name__}: {exc}")
                continue

            scores = [c.rerank_score for c in candidates if c.rerank_score is not None]
            top1 = scores[0] if scores else None
            out.append(
                {
                    "id": row["id"],
                    "query_type": row.get("query_type", "?"),
                    "query": query,
                    "top1_rerank": top1,
                    "mean_top3_rerank": (st.mean(scores[:3]) if scores else None),
                    "n_candidates": len(candidates),
                }
            )
            mark = f"{top1:+.4f}" if top1 is not None else "  none "
            print(f"  [{i:>3}/{len(rows)}] {row.get('query_type','?'):<12} {mark}  {query[:52]}")
    return out


def report(results: list[dict]) -> dict:
    by_type: dict[str, list[float]] = defaultdict(list)
    for r in results:
        if r["top1_rerank"] is not None:
            by_type[r["query_type"]].append(r["top1_rerank"])

    print()
    print("=== TOP-1 RERANK SCORE BY QUERY TYPE ===")
    print(f"  {'type':<14}{'n':>5}{'min':>10}{'p25':>10}{'median':>10}{'p75':>10}{'max':>10}")
    summary: dict[str, dict] = {}
    for qtype in TYPE_ORDER + [t for t in by_type if t not in TYPE_ORDER]:
        vals = by_type.get(qtype, [])
        if not vals:
            continue
        s = {
            "n": len(vals),
            "min": min(vals),
            "p25": percentile(vals, 25),
            "median": st.median(vals),
            "p75": percentile(vals, 75),
            "max": max(vals),
        }
        summary[qtype] = s
        print(
            f"  {qtype:<14}{s['n']:>5}{s['min']:>10.4f}{s['p25']:>10.4f}"
            f"{s['median']:>10.4f}{s['p75']:>10.4f}{s['max']:>10.4f}"
        )

    # Does the signal actually separate? This is the go/no-go for G2 option B.
    print()
    print("=== SEPARATION CHECK (the G2=B go/no-go) ===")
    clear = by_type.get("clear", [])
    harder = by_type.get("vague", []) + by_type.get("edge", [])
    verdict = "INSUFFICIENT DATA"
    if clear and harder:
        c_med, h_med = st.median(clear), st.median(harder)
        gap = c_med - h_med
        print(f"  median(clear)          = {c_med:+.4f}   n={len(clear)}")
        print(f"  median(edge+vague)     = {h_med:+.4f}   n={len(harder)}")
        print(f"  separation             = {gap:+.4f}")
        # Overlap: how many "harder" queries score above the clear median?
        above = sum(1 for v in harder if v >= c_med)
        overlap_pct = 100 * above / len(harder)
        print(f"  edge+vague above clear median: {above}/{len(harder)} ({overlap_pct:.0f}%)")
        if gap > 0.05 and overlap_pct < 35:
            verdict = "SEPARATES - a threshold is defensible"
        elif gap > 0:
            verdict = "WEAK - ordering is right but overlap is high; threshold will misroute"
        else:
            verdict = "DOES NOT SEPARATE - rerank score is not a usable routing signal here"
        print(f"\n  VERDICT: {verdict}")

    return {"by_type": summary, "verdict": verdict}


async def amain(limit: int | None, rerank_timeout: float) -> int:
    rows = load_golden(limit)
    print(f"Measuring rerank confidence over {len(rows)} golden queries...\n")
    results = await measure(rows, rerank_timeout=rerank_timeout)
    if not results:
        print("no results - is the data tier up and the corpus ingested?", file=sys.stderr)
        return 1
    summary = report(results)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"confidence-distribution-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "golden_set": str(GOLDEN.relative_to(REPO_ROOT)),
                "n_measured": len(results),
                **summary,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nresults: {path.relative_to(REPO_ROOT)}")
    return 0


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Measure rerank-score distribution by query type.")
    ap.add_argument("--limit", type=int, default=None, help="only the first N golden queries")
    ap.add_argument(
        "--rerank-timeout",
        type=float,
        default=30.0,
        help="seconds; deliberately >> the production 2.0s (see measure()).",
    )
    args = ap.parse_args()
    sys.exit(asyncio.run(amain(args.limit, args.rerank_timeout)))


if __name__ == "__main__":
    main()
