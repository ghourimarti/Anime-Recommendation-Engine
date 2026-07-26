"""Promote eval_report.json's advanced metrics into evals/baseline.json.

Used after an intentional metric shift in a PR: humans run this locally,
review the diff, and commit the baseline bump as part of the same PR.

    python scripts/eval_promote.py
    python scripts/eval_promote.py --from eval_report.json --to evals/baseline.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="src", type=Path, default=Path("eval_report.json"))
    parser.add_argument("--to", dest="dst", type=Path, default=Path("evals/baseline.json"))
    args = parser.parse_args()

    if not args.src.exists():
        print(f"source not found: {args.src} (run `make eval` first)", file=sys.stderr)
        return 2

    src = json.loads(args.src.read_text(encoding="utf-8"))
    metrics = src.get("advanced") or src.get("metrics")
    if not metrics:
        print(f"{args.src}: neither `advanced` nor `metrics` present", file=sys.stderr)
        return 2

    payload = {
        "embedding_model": src.get("embedding_model"),
        "generated_at": _dt.date.today().isoformat(),
        "metrics": metrics,
        "ragas": src.get("ragas"),
        "notes": (
            "Frozen baseline of the advanced retrieval pipeline. Update via "
            "`make eval && make eval-promote` on intentional metric shifts. "
            "See docs/repo-setup.md §6."
        ),
    }
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Promoted {args.src} -> {args.dst} (embedding_model={payload['embedding_model']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
