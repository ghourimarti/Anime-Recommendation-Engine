"""Eval regression comparator — the CI eval gate enforcement.

Compares two eval reports (baseline + candidate) and decides whether the
candidate has regressed the production retrieval pipeline beyond an
acceptable threshold.

Semantics:
  For each gated metric, compute:
      absolute_delta = candidate - baseline
      relative_delta = (candidate - baseline) / baseline   (0 if baseline == 0)
  A regression fires only when BOTH conditions hold:
      absolute_delta < -floor       (default floor = 0.01)
      relative_delta < -threshold   (default threshold = 0.03)
  The floor protects against noise on tiny metrics: a recall@3 drop from
  0.005 -> 0.001 is a 80% relative drop but only 0.004 absolute, and should
  not block a merge.

  distinct_ratio is reported but never gated (information only).

Exit codes:
  0 - no regressions; merge OK.
  1 - at least one gated metric regressed beyond threshold; merge blocked.
  2 - usage error (missing file, schema mismatch, etc.).

Schemas accepted:
  baseline.json shape:  {"embedding_model": ..., "metrics": {...}, ...}
  eval_report.json:     {"embedding_model": ..., "advanced": {...}, ...}
The comparator auto-discovers which schema each file uses.

This module is pure-stdlib so it runs even in CI matrices where `uv sync`
has not (yet) installed workspace extras. That is deliberate: the gate must
be runnable without the heavyweight retrieval / core import paths.

Usage:
    python -m anime_eval.compare --baseline evals/baseline.json --candidate eval_report.json
    python -m anime_eval.compare --baseline ... --candidate ... --threshold 0.03 --floor 0.01
    python -m anime_eval.compare ... --format markdown --output eval_gate.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anime_core.console import use_utf8_stdout

# Defaults — the eval gate.
DEFAULT_THRESHOLD: float = 0.03  # block if relative drop exceeds 3%
DEFAULT_FLOOR: float = 0.01  # and only if absolute drop also exceeds 0.01

# Gated metrics block merges; informational metrics are reported but not gated.
GATED_METRICS: tuple[str, ...] = (
    "success@1",
    "success@3",
    "precision@1",
    "precision@3",
    "recall@1",
    "recall@3",
    "ndcg@1",
    "ndcg@3",
    "mrr",
)
INFORMATIONAL_METRICS: tuple[str, ...] = ("distinct_ratio",)

# ── the lift gate ────────────────────────────────────────────────────────────
# Regression-vs-baseline is necessary but NOT sufficient, and the reranker outage
# is the proof. When the cross-encoder timed out on every request, the advanced
# pipeline silently degraded to plain hybrid order — so it scored *approximately
# naive*. Absolute numbers that merely drift toward naive can sit inside the
# regression tolerance while the entire advanced pipeline is doing nothing at all
# and still charging you its latency.
#
# So we assert the thing we actually believe: the advanced pipeline must BEAT
# dense-only retrieval. If it doesn't, the advanced stages aren't earning their
# keep, whatever the absolute scores say.
LIFT_METRICS: tuple[str, ...] = ("success@1", "mrr")
DEFAULT_MIN_LIFT: float = 0.01


@dataclass(frozen=True)
class MetricDelta:
    """One metric's baseline-vs-candidate comparison row."""

    name: str
    baseline: float
    candidate: float
    absolute_delta: float
    relative_delta: float
    is_regression: bool
    is_gated: bool

    @property
    def direction(self) -> str:
        if self.absolute_delta > 1e-9:
            return "↑"
        if self.absolute_delta < -1e-9:
            return "↓"
        return "·"


@dataclass(frozen=True)
class LiftCheck:
    """Advanced-vs-naive on one metric. See LIFT_METRICS for why this gate exists."""

    name: str
    naive: float
    advanced: float
    min_lift: float

    @property
    def lift(self) -> float:
        return self.advanced - self.naive

    @property
    def ok(self) -> bool:
        return self.lift >= self.min_lift


@dataclass(frozen=True)
class ComparisonResult:
    """Aggregated comparison outcome — what the CLI returns and what the renderers consume."""

    threshold: float
    floor: float
    deltas: list[MetricDelta] = field(default_factory=list)
    lifts: list[LiftCheck] = field(default_factory=list)
    baseline_path: str = ""
    candidate_path: str = ""
    baseline_embedding_model: str | None = None
    candidate_embedding_model: str | None = None

    @property
    def regressions(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.is_regression]

    @property
    def lift_failures(self) -> list[LiftCheck]:
        return [x for x in self.lifts if not x.ok]

    @property
    def ok(self) -> bool:
        # Both gates must pass. A run can be free of regressions and still be
        # broken — that is precisely the dead-reranker case.
        return not self.regressions and not self.lift_failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "threshold": self.threshold,
            "floor": self.floor,
            "baseline_path": self.baseline_path,
            "candidate_path": self.candidate_path,
            "baseline_embedding_model": self.baseline_embedding_model,
            "candidate_embedding_model": self.candidate_embedding_model,
            "regressions": [
                {
                    "metric": d.name,
                    "baseline": d.baseline,
                    "candidate": d.candidate,
                    "absolute_delta": d.absolute_delta,
                    "relative_delta": d.relative_delta,
                }
                for d in self.regressions
            ],
            "deltas": [
                {
                    "metric": d.name,
                    "baseline": d.baseline,
                    "candidate": d.candidate,
                    "absolute_delta": d.absolute_delta,
                    "relative_delta": d.relative_delta,
                    "is_regression": d.is_regression,
                    "is_gated": d.is_gated,
                }
                for d in self.deltas
            ],
            "lifts": [
                {
                    "metric": x.name,
                    "naive": x.naive,
                    "advanced": x.advanced,
                    "lift": x.lift,
                    "min_lift": x.min_lift,
                    "ok": x.ok,
                }
                for x in self.lifts
            ],
        }


def _load_naive(path: Path) -> dict[str, float]:
    """The candidate report's naive (dense-only) metrics, if it carries them.

    Only eval_report.json has a naive block; evals/baseline.json doesn't. Missing
    is not an error — it just means the lift gate has nothing to check.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    naive = payload.get("naive")
    return dict(naive) if isinstance(naive, dict) else {}


def _load_metrics(path: Path) -> tuple[dict[str, float], str | None]:
    """Read either schema and return ({metric_name: value}, embedding_model)."""
    if not path.exists():
        raise FileNotFoundError(f"Eval report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Schema 1: baseline.json - {embedding_model, metrics: {...}}
    if isinstance(payload.get("metrics"), dict):
        return dict(payload["metrics"]), payload.get("embedding_model")
    # Schema 2: eval_report.json - {embedding_model, advanced: {...}}
    if isinstance(payload.get("advanced"), dict):
        return dict(payload["advanced"]), payload.get("embedding_model")
    raise ValueError(
        f"{path}: expected either {{'metrics': ...}} or {{'advanced': ...}} at top level"
    )


def compare_reports(
    baseline_path: Path,
    candidate_path: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    floor: float = DEFAULT_FLOOR,
    min_lift: float = DEFAULT_MIN_LIFT,
) -> ComparisonResult:
    """Run the comparison. Caller decides what to do with the result."""
    baseline_metrics, baseline_model = _load_metrics(baseline_path)
    candidate_metrics, candidate_model = _load_metrics(candidate_path)
    naive_metrics = _load_naive(candidate_path)

    # Lift gate: does the advanced pipeline still beat dense-only retrieval?
    lifts = [
        LiftCheck(
            name=name,
            naive=float(naive_metrics[name]),
            advanced=float(candidate_metrics[name]),
            min_lift=min_lift,
        )
        for name in LIFT_METRICS
        if name in naive_metrics and name in candidate_metrics
    ]

    deltas: list[MetricDelta] = []
    seen: set[str] = set()

    # Canonical order first so output is deterministic.
    for name in (*GATED_METRICS, *INFORMATIONAL_METRICS):
        if name not in baseline_metrics or name not in candidate_metrics:
            continue
        seen.add(name)
        b = float(baseline_metrics[name])
        c = float(candidate_metrics[name])
        absolute = c - b
        relative = (absolute / b) if abs(b) > 1e-12 else 0.0
        is_gated = name in GATED_METRICS
        # Both gates must breach for regression. Floor protects tiny metrics
        # from triggering on noise; threshold protects all metrics from
        # triggering on absolute drops that are sizeable in % terms but small
        # in magnitude.
        is_regression = is_gated and absolute < -floor and relative < -threshold
        deltas.append(
            MetricDelta(
                name=name,
                baseline=b,
                candidate=c,
                absolute_delta=absolute,
                relative_delta=relative,
                is_regression=is_regression,
                is_gated=is_gated,
            )
        )

    # Extras present in both reports but not in canonical lists are reported
    # informationally (never gated).
    extras = (set(baseline_metrics) & set(candidate_metrics)) - seen
    for name in sorted(extras):
        b = float(baseline_metrics[name])
        c = float(candidate_metrics[name])
        absolute = c - b
        relative = (absolute / b) if abs(b) > 1e-12 else 0.0
        deltas.append(
            MetricDelta(
                name=name,
                baseline=b,
                candidate=c,
                absolute_delta=absolute,
                relative_delta=relative,
                is_regression=False,
                is_gated=False,
            )
        )

    return ComparisonResult(
        threshold=threshold,
        floor=floor,
        deltas=deltas,
        lifts=lifts,
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
        baseline_embedding_model=baseline_model,
        candidate_embedding_model=candidate_model,
    )


def render_markdown(result: ComparisonResult) -> str:
    """GitHub-flavored markdown for sticky PR comment."""
    lines: list[str] = []
    status = "✅ **PASS**" if result.ok else "❌ **REGRESSION**"
    lines.append(f"### Eval gate: {status}")
    lines.append("")
    lines.append(
        f"_Threshold: relative drop > {result.threshold:.0%} AND "
        f"absolute drop > {result.floor:.3f} blocks merge._"
    )
    if (
        result.baseline_embedding_model
        and result.candidate_embedding_model
        and result.baseline_embedding_model != result.candidate_embedding_model
    ):
        lines.append("")
        lines.append(
            f"> ⚠️ Embedding model changed: "
            f"`{result.baseline_embedding_model}` -> `{result.candidate_embedding_model}`. "
            f"IR-metric shifts may reflect that change, not a code regression."
        )
    lines.append("")
    lines.append("| Metric | Baseline | Candidate | Δ abs | Δ rel | Gated | Regression? |")
    lines.append("|---|---:|---:|---:|---:|:---:|:---:|")
    for d in result.deltas:
        flag = "\U0001f6ab" if d.is_regression else ("·" if not d.is_gated else "✓")
        lines.append(
            f"| {d.name} | {d.baseline:.3f} | {d.candidate:.3f} {d.direction} | "
            f"{d.absolute_delta:+.3f} | {d.relative_delta:+.2%} | "
            f"{'✓' if d.is_gated else '·'} | {flag} |"
        )
    if result.regressions:
        lines.append("")
        lines.append("**Regressed metrics:** " + ", ".join(d.name for d in result.regressions))
    return "\n".join(lines) + "\n"


def render_text(result: ComparisonResult) -> str:
    """Terminal-friendly text for local dev runs."""
    lines: list[str] = []
    status = "PASS" if result.ok else "REGRESSION"
    lines.append(f"Eval gate: {status}")
    lines.append(f"Threshold relative={result.threshold:.0%} floor={result.floor:.3f}")
    lines.append(f"Baseline:  {result.baseline_path}")
    lines.append(f"Candidate: {result.candidate_path}")
    if (
        result.baseline_embedding_model
        and result.candidate_embedding_model
        and result.baseline_embedding_model != result.candidate_embedding_model
    ):
        lines.append(
            f"NOTE: embedding model changed "
            f"({result.baseline_embedding_model} -> {result.candidate_embedding_model})"
        )
    lines.append("")
    lines.append(f"{'metric':<16} {'baseline':>10} {'candidate':>10} {'d-abs':>9} {'d-rel':>9}")
    lines.append("-" * 56)
    for d in result.deltas:
        marker = " "
        if d.is_regression:
            marker = "!"
        elif not d.is_gated:
            marker = "."
        lines.append(
            f"{d.name:<16} {d.baseline:>10.3f} {d.candidate:>10.3f} "
            f"{d.absolute_delta:>+9.3f} {d.relative_delta:>+9.2%} {marker}"
        )
    if result.regressions:
        lines.append("")
        lines.append("Regressed metrics: " + ", ".join(d.name for d in result.regressions))

    if result.lifts:
        lines.append("")
        lines.append(f"Lift over naive (advanced must win by >= {result.lifts[0].min_lift:+.3f}):")
        lines.append(f"{'metric':<16} {'naive':>10} {'advanced':>10} {'lift':>9}")
        lines.append("-" * 48)
        for x in result.lifts:
            lines.append(
                f"{x.name:<16} {x.naive:>10.3f} {x.advanced:>10.3f} "
                f"{x.lift:>+9.3f} {'' if x.ok else '!'}"
            )
        if result.lift_failures:
            lines.append("")
            lines.append(
                "NO LIFT: "
                + ", ".join(x.name for x in result.lift_failures)
                + " — the advanced pipeline is not beating dense-only retrieval, so it is "
                "paying rerank+MMR latency for nothing. Check the reranker is actually "
                "running (a timeout degrades it to plain hybrid order, silently)."
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    use_utf8_stdout()

    parser = argparse.ArgumentParser(
        prog="python -m anime_eval.compare",
        description="Compare a candidate eval report to a frozen baseline. Exits 1 on regression.",
    )
    parser.add_argument("--baseline", type=Path, required=True, help="Path to evals/baseline.json")
    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Path to eval_report.json (or any file matching either schema)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Relative-drop threshold (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=DEFAULT_FLOOR,
        help=f"Absolute-drop floor (default {DEFAULT_FLOOR})",
    )
    parser.add_argument(
        "--min-lift",
        type=float,
        default=DEFAULT_MIN_LIFT,
        help=(
            f"Minimum advantage the advanced pipeline must hold over naive on "
            f"{'/'.join(LIFT_METRICS)} (default {DEFAULT_MIN_LIFT}). Only checked when the "
            f"candidate report carries a 'naive' block."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "text"),
        default="text",
        help="Output format (default text)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="If set, write the formatted output to this path instead of stdout",
    )
    args = parser.parse_args(argv)

    try:
        result = compare_reports(
            args.baseline,
            args.candidate,
            threshold=args.threshold,
            floor=args.floor,
            min_lift=args.min_lift,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        payload = json.dumps(result.to_dict(), indent=2) + "\n"
    elif args.format == "markdown":
        payload = render_markdown(result)
    else:
        payload = render_text(result)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
