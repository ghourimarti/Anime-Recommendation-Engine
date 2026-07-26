"""Tests for anime_eval.compare - the CI regression gate.

Covers:
  - Schema discovery (baseline.json AND eval_report.json shapes both parse)
  - Threshold semantics (relative drop + absolute floor)
  - distinct_ratio is informational only (never gates)
  - Error paths (missing file, unknown schema)
  - Renderers (markdown, text, json) — content and shape
  - CLI exit codes (0 pass / 1 regression / 2 usage)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from anime_eval.compare import (
    DEFAULT_FLOOR,
    DEFAULT_THRESHOLD,
    compare_reports,
    main,
    render_markdown,
    render_text,
)


def _write_baseline(path: Path, metrics: dict[str, float]) -> Path:
    path.write_text(
        json.dumps(
            {
                "embedding_model": "text-embedding-3-small",
                "metrics": metrics,
                "ragas": None,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_report(
    path: Path,
    advanced: dict[str, float],
    naive: dict[str, float] | None = None,
) -> Path:
    # The default naive block is deliberately WORSE than advanced — i.e. a healthy
    # pipeline where reranking is actually earning something. It used to default to
    # `advanced` itself, which is the exact signature of a DEAD reranker (advanced
    # degrades to hybrid order and scores identically to naive). With the lift gate
    # in place that default would quietly inject a gate failure into every test that
    # only meant to exercise schema parsing.
    if naive is None:
        naive = {k: max(0.0, v - 0.08) for k, v in advanced.items()}
    path.write_text(
        json.dumps(
            {
                "embedding_model": "text-embedding-3-small",
                "naive": naive,
                "advanced": advanced,
                "comparison": {},
                "ragas": None,
            }
        ),
        encoding="utf-8",
    )
    return path


def _all_passing(success_3: float = 0.82) -> dict[str, float]:
    """Canonical 'all metrics healthy' snapshot used as both sides of equality tests."""
    return {
        "success@1": 0.68,
        "success@3": success_3,
        "precision@1": 0.68,
        "precision@3": 0.30,
        "recall@1": 0.54,
        "recall@3": 0.62,
        "ndcg@1": 0.68,
        "ndcg@3": 0.64,
        "mrr": 0.74,
        "distinct_ratio": 1.0,
    }


# ──────────────────────────────────────────────────
# Schema discovery
# ──────────────────────────────────────────────────


def test_loads_baseline_json_schema(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "baseline.json", _all_passing())
    candidate = _write_baseline(tmp_path / "candidate.json", _all_passing())
    result = compare_reports(baseline, candidate)
    assert result.ok
    assert result.baseline_embedding_model == "text-embedding-3-small"


def test_loads_eval_report_json_schema(tmp_path: Path) -> None:
    baseline = _write_report(tmp_path / "baseline_full.json", _all_passing())
    candidate = _write_report(tmp_path / "candidate_full.json", _all_passing())
    result = compare_reports(baseline, candidate)
    assert result.ok


def test_mixed_schemas_parse(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "baseline.json", _all_passing())
    candidate = _write_report(tmp_path / "report.json", _all_passing())
    result = compare_reports(baseline, candidate)
    assert result.ok


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compare_reports(tmp_path / "missing.json", tmp_path / "also-missing.json")


def test_unknown_schema_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"unrelated": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        compare_reports(bad, bad)


# ──────────────────────────────────────────────────
# Threshold semantics
# ──────────────────────────────────────────────────


def test_no_regression_when_unchanged(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    result = compare_reports(baseline, candidate)
    assert result.ok
    assert result.regressions == []


def test_improvement_is_not_regression(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    better = _all_passing()
    better["success@3"] = 0.90  # large improvement
    candidate = _write_baseline(tmp_path / "c.json", better)
    result = compare_reports(baseline, candidate)
    assert result.ok


def test_tiny_absolute_drop_blocked_by_floor(tmp_path: Path) -> None:
    """A huge relative drop with tiny absolute movement does NOT block."""
    baseline_m = _all_passing()
    baseline_m["recall@3"] = 0.005
    candidate_m = _all_passing()
    candidate_m["recall@3"] = 0.001  # 80% relative, 0.004 absolute (under floor=0.01)
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate)
    assert result.ok, f"Floor should suppress noise; regressions={result.regressions}"


def test_relative_below_threshold_does_not_fire(tmp_path: Path) -> None:
    """A 2.4% relative drop with sufficient absolute drop is still under 3% threshold."""
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.80  # 0.82 -> 0.80 = 2.44% rel, 0.02 abs
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate)
    assert result.ok, f"2.44% drop should not fire 3% gate; regressions={result.regressions}"


def test_relative_above_threshold_with_absolute_drop_fires(tmp_path: Path) -> None:
    """A 4.88% relative drop with 0.04 absolute drop fires the gate."""
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.78  # 0.82 -> 0.78 = 4.88% rel, 0.04 abs
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate)
    assert not result.ok
    assert [d.name for d in result.regressions] == ["success@3"]


def test_multiple_regressions_all_reported(tmp_path: Path) -> None:
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.70  # big drop
    candidate_m["ndcg@3"] = 0.50  # big drop
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate)
    assert not result.ok
    regressed = {d.name for d in result.regressions}
    assert regressed == {"success@3", "ndcg@3"}


def test_distinct_ratio_is_informational(tmp_path: Path) -> None:
    """distinct_ratio dropping never blocks — it is information only."""
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["distinct_ratio"] = 0.30  # would otherwise be a huge regression
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate)
    assert result.ok
    distinct = next(d for d in result.deltas if d.name == "distinct_ratio")
    assert not distinct.is_gated


def test_threshold_override(tmp_path: Path) -> None:
    """Lowering the threshold to 1% makes a 2.44% drop fire."""
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.80
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate, threshold=0.01)
    assert not result.ok


def test_floor_override(tmp_path: Path) -> None:
    """Raising the floor to 0.05 suppresses a 0.04 absolute drop."""
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.78  # would otherwise fire (0.04 abs, 4.88% rel)
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    result = compare_reports(baseline, candidate, floor=0.05)
    assert result.ok


# ──────────────────────────────────────────────────
# Renderers
# ──────────────────────────────────────────────────


def test_markdown_pass(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    md = render_markdown(compare_reports(baseline, candidate))
    assert "PASS" in md
    assert "| Metric |" in md
    assert "success@3" in md


def test_markdown_regression(tmp_path: Path) -> None:
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.70
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    md = render_markdown(compare_reports(baseline, candidate))
    assert "REGRESSION" in md
    assert "success@3" in md


def test_markdown_flags_embedding_model_change(tmp_path: Path) -> None:
    baseline = tmp_path / "b.json"
    baseline.write_text(
        json.dumps(
            {
                "embedding_model": "text-embedding-3-small",
                "metrics": _all_passing(),
                "ragas": None,
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "c.json"
    candidate.write_text(
        json.dumps(
            {
                "embedding_model": "text-embedding-3-large",
                "metrics": _all_passing(),
                "ragas": None,
            }
        ),
        encoding="utf-8",
    )
    md = render_markdown(compare_reports(baseline, candidate))
    assert "Embedding model changed" in md


def test_text_renders(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    txt = render_text(compare_reports(baseline, candidate))
    assert "Eval gate: PASS" in txt
    assert "success@3" in txt


def test_to_dict_roundtrip(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    payload = compare_reports(baseline, candidate).to_dict()
    assert payload["ok"] is True
    assert payload["threshold"] == DEFAULT_THRESHOLD
    assert payload["floor"] == DEFAULT_FLOOR
    assert any(d["metric"] == "success@3" for d in payload["deltas"])


# ──────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────


def test_cli_exit_0_on_pass(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    exit_code = main(["--baseline", str(baseline), "--candidate", str(candidate)])
    assert exit_code == 0


def test_cli_exit_1_on_regression(tmp_path: Path) -> None:
    baseline_m = _all_passing()
    candidate_m = _all_passing()
    candidate_m["success@3"] = 0.70
    baseline = _write_baseline(tmp_path / "b.json", baseline_m)
    candidate = _write_baseline(tmp_path / "c.json", candidate_m)
    exit_code = main(["--baseline", str(baseline), "--candidate", str(candidate)])
    assert exit_code == 1


def test_cli_exit_2_on_missing_file(tmp_path: Path) -> None:
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    exit_code = main(["--baseline", str(tmp_path / "missing.json"), "--candidate", str(candidate)])
    assert exit_code == 2


def test_cli_writes_output_file(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    out = tmp_path / "report.md"
    exit_code = main(
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--format",
            "markdown",
            "--output",
            str(out),
        ]
    )
    assert exit_code == 0
    assert out.exists()
    assert "PASS" in out.read_text(encoding="utf-8")


def test_cli_format_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = _write_baseline(tmp_path / "b.json", _all_passing())
    candidate = _write_baseline(tmp_path / "c.json", _all_passing())
    exit_code = main(
        ["--baseline", str(baseline), "--candidate", str(candidate), "--format", "json"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert any(d["metric"] == "success@3" for d in payload["deltas"])


# ── the lift gate: does the advanced pipeline actually beat naive? ────────────


def test_dead_reranker_fails_the_gate_even_with_no_regression(tmp_path: Path) -> None:
    """THE regression test for the reranker outage.

    When the cross-encoder times out, the advanced pipeline degrades to plain
    hybrid order and scores *the same as naive*. Crucially it can do that while
    still sitting inside the regression tolerance versus a baseline — so a gate
    that only compares against the baseline sees nothing wrong, and the whole
    advanced pipeline goes on burning rerank+MMR latency for zero benefit.

    Here the candidate matches the baseline EXACTLY (zero regression), and the gate
    must still fail, purely because advanced == naive.
    """
    metrics = {"success@1": 0.68, "mrr": 0.74, "ndcg@3": 0.64}
    baseline = _write_baseline(tmp_path / "baseline.json", metrics)
    # advanced == naive: exactly what a timed-out reranker produces.
    candidate = _write_report(tmp_path / "report.json", advanced=metrics, naive=metrics)

    result = compare_reports(baseline, candidate)

    assert not result.regressions, "sanity: this candidate has NOT regressed vs baseline"
    assert not result.ok, "but it must still FAIL — the advanced pipeline earns nothing"
    assert {x.name for x in result.lift_failures} == {"success@1", "mrr"}


def test_healthy_lift_passes(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path / "baseline.json", {"success@1": 0.68, "mrr": 0.74})
    candidate = _write_report(
        tmp_path / "report.json",
        advanced={"success@1": 0.68, "mrr": 0.74},
        naive={"success@1": 0.59, "mrr": 0.67},
    )
    result = compare_reports(baseline, candidate)
    assert result.ok
    assert [round(x.lift, 3) for x in result.lifts] == [0.09, 0.07]


def test_lift_below_floor_fails(tmp_path: Path) -> None:
    """A sliver of lift is not lift. The advanced stages must clear the floor."""
    baseline = _write_baseline(tmp_path / "baseline.json", {"success@1": 0.68, "mrr": 0.74})
    candidate = _write_report(
        tmp_path / "report.json",
        advanced={"success@1": 0.68, "mrr": 0.74},
        naive={"success@1": 0.675, "mrr": 0.735},  # +0.005 — under the 0.01 floor
    )
    result = compare_reports(baseline, candidate)
    assert not result.ok
    assert {x.name for x in result.lift_failures} == {"success@1", "mrr"}


def test_baseline_only_report_skips_the_lift_gate(tmp_path: Path) -> None:
    """Comparing two baseline-shaped files has no naive block — nothing to check.

    Absence of a naive block must not be treated as a failure, or every
    baseline-vs-baseline comparison would explode.
    """
    baseline = _write_baseline(tmp_path / "baseline.json", {"success@1": 0.68})
    candidate = _write_baseline(tmp_path / "cand.json", {"success@1": 0.68})
    result = compare_reports(baseline, candidate)
    assert result.lifts == []
    assert result.ok


def test_lift_failure_is_reported_in_text_output(tmp_path: Path) -> None:
    """The operator must be told WHY, not just handed exit 1."""
    metrics = {"success@1": 0.68, "mrr": 0.74}
    baseline = _write_baseline(tmp_path / "baseline.json", metrics)
    candidate = _write_report(tmp_path / "report.json", advanced=metrics, naive=metrics)
    text = render_text(compare_reports(baseline, candidate))
    assert "NO LIFT" in text
    assert "reranker" in text  # points at the actual likely cause


def test_cli_exits_1_on_lift_failure(tmp_path: Path) -> None:
    metrics = {"success@1": 0.68, "mrr": 0.74}
    baseline = _write_baseline(tmp_path / "baseline.json", metrics)
    candidate = _write_report(tmp_path / "report.json", advanced=metrics, naive=metrics)
    rc = main(["--baseline", str(baseline), "--candidate", str(candidate)])
    assert rc == 1
