#!/usr/bin/env python3
"""Venue routing quality + cost A/B (S21.8).

THE QUESTION THIS ANSWERS
-------------------------
Not "does the app still work with the flag on" - that is nearly guaranteed,
because 74% of queries never reach the venue and the rest fall through on
failure. The real question is narrower and harder:

    For the queries the venue ACTUALLY TAKES, is its answer as good as the
    hosted chain would have produced for the same query?

WHY NOT `make eval`
-------------------
`make eval` is retrieval-only - it takes a QueryRetriever and computes IR
metrics. It never calls an LLM, so flag-off and flag-on produce identical
numbers. Reporting that as "no regression" would be a false assurance about a
code path the eval does not execute.

WHY NOT `make eval-refusal` ALONE
---------------------------------
It does run the full service, but its adversarial queries score <= -9.70 on
rerank confidence - far below the 1.0 routing threshold - so they go to the
hosted chain and never exercise the venue. It is a necessary gate, not a
sufficient one.

WHAT THIS DOES
--------------
Runs the same golden queries through the real service THREE times:

    pass 1  routing OFF   baseline
    pass 2  routing OFF   CONTROL - identical config, so every difference
                          between pass 1 and 2 is provider non-determinism
    pass 3  routing ON

The control pass exists because the first version of this script did not have
one, compared a single off-pass to a single on-pass, and promptly "failed" on a
query with confidence -9.0 that routing never touched. LLM output is not
deterministic even at temperature 0. Without a noise floor, that script would
attribute provider noise to the feature under test.

COST: three LLM calls per query. Use --limit while iterating.

Usage:
    uv run python scripts/venue/eval_routing.py --limit 10
    uv run python scripts/venue/eval_routing.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anime_core.db.engine import session_scope
from anime_core.embeddings import OpenAIEmbedder
from anime_core.venue import venue_confidence_threshold
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "packages" / "eval" / "src" / "anime_eval" / "golden_sets" / "v1.jsonl"
OUT_DIR = REPO_ROOT / "Documents" / "docs" / "venue-bench"


def load_golden(limit: int | None) -> list[dict]:
    rows = [
        json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return rows[:limit] if limit else rows


async def run_pass(rows: list[dict], *, routing_enabled: bool) -> list[dict]:
    """One full pass over the golden set with routing on or off."""
    import os

    os.environ["LLM_VENUE_ROUTING_ENABLED"] = "true" if routing_enabled else "false"

    # Imported INSIDE the pass so the client is rebuilt against the env just set.
    from anime_core.llm_client import build_default_llm_client
    from anime_core.venue import RETRIEVAL_CONFIDENCE
    from anime_retrieval.pipeline import RetrievalPipeline
    from anime_retrieval.service import RecommendationService

    embedder = OpenAIEmbedder()
    out: list[dict] = []

    async with session_scope() as session:
        # Generous rerank timeout for the same reason as measure_confidence.py:
        # at the production 2.0s a cold cross-encoder yields rerank_score=None,
        # every query routes to hosted, and the A/B would compare hosted to
        # hosted while appearing to pass.
        pipeline = RetrievalPipeline(session=session, embedder=embedder, rerank_timeout=30.0)
        llm = build_default_llm_client()
        service = RecommendationService(retriever=pipeline, llm=llm)

        # Warm the reranker so query #1 is not the one that pays model load.
        with contextlib.suppress(Exception):
            await service.recommend("warmup query")

        for i, row in enumerate(rows, 1):
            query = row["query"]
            try:
                result = await service.recommend(query)
                confidence = RETRIEVAL_CONFIDENCE.get()
                out.append(
                    {
                        "id": row["id"],
                        "query_type": row.get("query_type", "?"),
                        "query": query,
                        "confidence": confidence,
                        "eligible": confidence is not None
                        and confidence >= venue_confidence_threshold(),
                        "mal_ids": [item.mal_id for item in result.items],
                        "n_items": len(result.items),
                        "refusal": result.refusal,
                    }
                )
            except Exception as exc:
                out.append(
                    {
                        "id": row["id"],
                        "query_type": row.get("query_type", "?"),
                        "query": query,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            mode = "ON " if routing_enabled else "OFF"
            print(f"  [{mode}] [{i:>3}/{len(rows)}] {row['id']}")

    return out


def _diff(a: list[dict], b: list[dict]) -> dict[str, Any]:
    """Per-query differences between two passes, split by venue eligibility."""
    by_id = {r["id"]: r for r in a}
    eligible_changed: list[dict] = []
    ineligible_changed: list[dict] = []
    refusal_flips: list[dict] = []
    lost_items: list[dict] = []

    for r_b in b:
        r_a = by_id.get(r_b["id"])
        if not r_a or "error" in r_b or "error" in r_a:
            continue
        if bool(r_a["refusal"]) != bool(r_b["refusal"]):
            refusal_flips.append({"id": r_b["id"], "a": r_a["refusal"], "b": r_b["refusal"]})
        if r_b["n_items"] < r_a["n_items"]:
            lost_items.append({"id": r_b["id"], "a": r_a["n_items"], "b": r_b["n_items"]})
        if r_a["mal_ids"] != r_b["mal_ids"]:
            entry = {
                "id": r_b["id"],
                "query_type": r_b["query_type"],
                "confidence": r_b["confidence"],
                "a_ids": r_a["mal_ids"],
                "b_ids": r_b["mal_ids"],
            }
            (eligible_changed if r_b["eligible"] else ineligible_changed).append(entry)

    return {
        "eligible_changed": eligible_changed,
        "ineligible_changed": ineligible_changed,
        "refusal_flips": refusal_flips,
        "lost_items": lost_items,
    }


def compare(off_a: list[dict], off_b: list[dict], on: list[dict]) -> dict[str, Any]:
    """Compare routing-on against a NOISE FLOOR, not against a single baseline.

    WHY A CONTROL PASS EXISTS
    -------------------------
    The first version of this script compared one routing-off pass against one
    routing-on pass and reported any per-query difference as a routing effect.
    It immediately "failed": a query with confidence -9.0 - nowhere near the 1.0
    threshold, hosted in BOTH passes - returned a different recommendation set.

    Routing cannot explain that, because routing never touched it. LLM
    generation is simply not deterministic, even at temperature 0; Groq
    especially. So the original design attributed provider noise to the feature
    under test, and would have done so in whichever direction happened to look
    worse.

    The fix is a control group. off_a vs off_b is two IDENTICAL configurations,
    so every difference between them is noise. That is the floor. Routing only
    has a measurable effect if off_a vs on differs by MORE than that floor.
    """
    noise = _diff(off_a, off_b)
    effect = _diff(off_a, on)

    n = len([r for r in on if "error" not in r])
    n_eligible = len([r for r in on if r.get("eligible")])

    print()
    print("=== ROUTING ===")
    print(f"  queries compared                {n}")
    print(
        f"  venue-eligible (>= {venue_confidence_threshold()})         "
        f"{n_eligible} ({100 * n_eligible / max(n, 1):.0f}%)"
    )

    print()
    print("=== NOISE FLOOR (off vs off - identical config, so this is provider noise) ===")
    print(
        f"  recommendation set changed      {len(noise['eligible_changed']) + len(noise['ineligible_changed'])}/{n}"
    )
    print(f"    of which below threshold      {len(noise['ineligible_changed'])}")
    print(f"  refusal flips                   {len(noise['refusal_flips'])}")
    print(f"  fewer grounded items            {len(noise['lost_items'])}")

    print()
    print("=== ROUTING EFFECT (off vs on) ===")
    print(
        f"  recommendation set changed      {len(effect['eligible_changed']) + len(effect['ineligible_changed'])}/{n}"
    )
    print(f"    of which below threshold      {len(effect['ineligible_changed'])}")
    print(f"  refusal flips                   {len(effect['refusal_flips'])}")
    print(f"  fewer grounded items            {len(effect['lost_items'])}")

    # Below-threshold queries are hosted in both passes, so their change rate
    # should be indistinguishable from the noise floor. If routing-on moves them
    # MORE than noise does, routing is leaking into queries it must not touch.
    noise_ineligible = len(noise["ineligible_changed"])
    effect_ineligible = len(effect["ineligible_changed"])
    noise_lost = len(noise["lost_items"])
    effect_lost = len(effect["lost_items"])

    print()
    print("=== VERDICT ===")
    print(f"  below-threshold changes: noise={noise_ineligible}  routing={effect_ineligible}")
    print(f"  fewer-item queries:      noise={noise_lost}  routing={effect_lost}")

    # Counts this small are dominated by sampling variation, so a bare
    # `effect > noise` test fails on differences that mean nothing - 4 vs 3 on
    # twelve queries is not evidence of anything. Both quantities are counts of
    # rare-ish events, so allow roughly two standard deviations of a Poisson
    # count before calling a difference real. Crude, but it is an explicit
    # threshold rather than an implicit one, and it is stated in the output so
    # a reader can disagree with it.
    def _margin(baseline: int) -> float:
        return 2 * math.sqrt(baseline + 1)

    ineligible_margin = _margin(noise_ineligible)
    lost_margin = _margin(noise_lost)
    print(
        f"  significance margin (~2 sd):  below-threshold +{ineligible_margin:.1f}"
        f"   fewer-item +{lost_margin:.1f}"
    )

    if effect_ineligible > noise_ineligible + ineligible_margin:
        verdict = (
            f"FAIL - below-threshold queries changed more with routing on "
            f"({effect_ineligible}) than noise ({noise_ineligible}) by more than the "
            f"margin; routing is leaking into queries it must not touch"
        )
    elif effect_lost > noise_lost + lost_margin:
        verdict = (
            f"INVESTIGATE - routing lost grounded items ({effect_lost}) above the "
            f"noise floor ({noise_lost}) by more than the margin; the 7B is likely "
            f"producing fewer groundable recommendations"
        )
    elif len(effect["refusal_flips"]) > len(noise["refusal_flips"]) + _margin(
        len(noise["refusal_flips"])
    ):
        verdict = "INVESTIGATE - refusal behaviour differs beyond the noise floor"
    else:
        verdict = "PASS - routing effect is within the provider-noise floor"
    print(f"\n  {verdict}")

    return {
        "n_compared": n,
        "n_eligible": n_eligible,
        "noise": noise,
        "effect": effect,
        "verdict": verdict,
    }


async def amain(limit: int | None) -> int:
    rows = load_golden(limit)
    print(f"Venue routing A/B over {len(rows)} golden queries (3 LLM calls each).\n")

    print("--- PASS 1: routing OFF (baseline) ---")
    off_a = await run_pass(rows, routing_enabled=False)
    print("\n--- PASS 2: routing OFF again (CONTROL - measures provider noise) ---")
    off_b = await run_pass(rows, routing_enabled=False)
    print("\n--- PASS 3: routing ON ---")
    on = await run_pass(rows, routing_enabled=True)

    summary = compare(off_a, off_b, on)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"routing-ab-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "threshold": venue_confidence_threshold(),
                **summary,
                "off_a": off_a,
                "off_b": off_b,
                "on": on,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nresults: {path.relative_to(REPO_ROOT)}")
    return 0 if summary["verdict"].startswith("PASS") else 1


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Venue routing quality A/B.")
    ap.add_argument("--limit", type=int, default=None, help="first N golden queries")
    args = ap.parse_args()
    sys.exit(asyncio.run(amain(args.limit)))


if __name__ == "__main__":
    main()
