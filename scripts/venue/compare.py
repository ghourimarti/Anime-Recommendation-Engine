#!/usr/bin/env python3
"""Compare two venue benchmark results — vLLM vs SGLang (S20.6).

Reads the newest result file per engine from Documents/docs/venue-bench/ and
prints a head-to-head. Verifies condition parity FIRST: if the controlled
variables differ, the comparison is void and says so rather than quietly
reporting a meaningless delta.

Two things this deliberately does not do:

  - Compare raw E2E latency. The engines emit slightly different output
    lengths at temperature 0, so E2E is confounded. The length-normalised
    figure at the bottom is the honest total-time comparison.
  - Declare a winner. A 3% throughput delta is not a decision; operational
    factors (image size, cold-start, ecosystem maturity) usually dominate.
    See docs/GPU_VENUE.md for the reasoning.

Usage:
    python scripts/venue/compare.py
    python scripts/venue/compare.py --dir Documents/docs/venue-bench
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "Documents" / "docs" / "venue-bench"

# Variables that MUST match for the comparison to mean anything.
CONTROLLED = [
    "model",
    "prompt_fixture_version",
    "max_tokens",
    "temperature",
    "runs_measured",
    "runs_warmup",
]


def newest(directory: Path, engine: str) -> dict:
    files = sorted(directory.glob(f"{engine}-*.json"))
    if not files:
        raise SystemExit(f"no results for '{engine}' in {directory}")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare venue benchmark results.")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--a", default="vllm")
    ap.add_argument("--b", default="sglang")
    args = ap.parse_args()

    a, b = newest(args.dir, args.a), newest(args.dir, args.b)

    print("=== CONDITION PARITY ===")
    drift = []
    for key in CONTROLLED:
        same = a.get(key) == b.get(key)
        if not same:
            drift.append(key)
        print(
            f"  [{'OK ' if same else 'DIFF'}] {key:<24} {args.a}={a.get(key)}  {args.b}={b.get(key)}"
        )

    # Free VRAM is reported but NOT treated as controlled: S19 established it
    # does not predict performance on a WDDM host (the clean run had less free
    # VRAM than the contended one and was faster).
    print(
        f"  [--] {'gpu_free_at_start':<24} "
        f"{args.a}={a['gpu'].get('memory_free_mib')} MiB  "
        f"{args.b}={b['gpu'].get('memory_free_mib')} MiB   (not predictive - see GPU_VENUE.md sec 5)"
    )

    if drift:
        print(f"\n  !! COMPARISON VOID — controlled variables differ: {', '.join(drift)}")
        print("     Re-run both engines with matching settings before comparing.")
        return 1

    print("\n=== HEAD TO HEAD ===")
    print(f"{'metric':<18}{args.a:>10}{args.b:>10}{'better':>10}{'margin':>10}")
    rows = [
        ("TTFT p50", "ttft_ms", "p50", False),
        ("TTFT p95", "ttft_ms", "p95", False),
        ("TTFT p99", "ttft_ms", "p99", False),
        ("TPOT p50", "tpot_ms", "p50", False),
        ("TPOT p99", "tpot_ms", "p99", False),
        ("tok/s p50", "output_tok_s", "p50", True),
    ]
    for label, key, pct, higher_is_better in rows:
        x, y = a["summary"][key][pct], b["summary"][key][pct]
        better = args.b if ((y > x) if higher_is_better else (y < x)) else args.a
        margin = max(x, y) / min(x, y)
        print(f"{label:<18}{x:>10.1f}{y:>10.1f}{better:>10}{margin:>9.2f}x")

    # Length-normalised total time: the honest end-to-end comparison.
    n = round((a["summary"]["output_tokens"]["mean"] + b["summary"]["output_tokens"]["mean"]) / 2)
    print(f"\n=== LENGTH-NORMALISED (same {n} output tokens) ===")
    for name, d in ((args.a, a), (args.b, b)):
        total = d["summary"]["ttft_ms"]["p50"] + n * d["summary"]["tpot_ms"]["p50"]
        print(f"  {name:<8} {total:>8.0f} ms")

    print(
        f"\n  Raw E2E is NOT comparable - output lengths differ "
        f"({args.a} {a['summary']['output_tokens']['mean']:.1f} tok, "
        f"{args.b} {b['summary']['output_tokens']['mean']:.1f} tok)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
