"""Cross-file config invariants.

Every bug these tests guard against has the same shape: two files that must agree,
no mechanism forcing them to, and a failure mode that is SILENT. Nothing crashes.
A dashboard just renders an empty panel, or a gate just stops matching anything and
waves the deploy through. You find out from a customer.

Config drift is not a tidiness problem. It is the reason the canary analysis was
querying a metric name the app never emitted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
HELM_VALUES = REPO_ROOT / "infra/k8s/helm/anime-recommender/values.yaml"
DASHBOARD = REPO_ROOT / "infra/observability/grafana/dashboards/api-overview.json"
ANALYSIS_TEMPLATE = (
    REPO_ROOT / "infra/k8s/helm/anime-recommender/templates/api-analysistemplate.yaml"
)


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_service_name_matches_helm_canary_filter() -> None:
    """OTEL_SERVICE_NAME becomes the `service_name` Prometheus label.

    The canary AnalysisTemplate and every Grafana panel filter on it. If they drift,
    the panels go blank and the canary matches no series — and a PromQL query over no
    data does not FAIL an Argo analysis, it passes. The rollout gets a green tick from
    a gate that measured nothing.

    .env.example shipped `anime-api` while the running system used `anime-rag-api`, so
    anyone starting from the documented template would have had exactly that.
    """
    env_name = _env_example()["OTEL_SERVICE_NAME"]
    helm = HELM_VALUES.read_text(encoding="utf-8")
    match = re.search(r"^\s*serviceName:\s*(\S+)\s*$", helm, flags=re.MULTILINE)
    assert match, "helm values has no api.canary.analysis.serviceName"
    assert env_name == match.group(1), (
        f"OTEL_SERVICE_NAME={env_name!r} but helm canary filters on {match.group(1)!r} — "
        "the canary would match zero series and pass every deploy"
    )


# Suffixes the OTel→Prometheus translation appends. The UNIT lands in the name too
# (unit="s" on anime.http.duration exports as anime_http_duration_SECONDS_bucket), which
# is exactly the kind of detail that makes "just grep for the metric name" quietly wrong.
_PROM_SUFFIXES = ("_seconds", "_bytes", "_total", "_bucket", "_sum", "_count")


def _base_metric(name: str) -> str:
    """Strip Prometheus' generated suffixes back to the instrument's base name."""
    changed = True
    while changed:
        changed = False
        for suffix in _PROM_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                changed = True
    return name


def _emitted_instruments() -> set[str]:
    src = (REPO_ROOT / "packages/core/src/anime_core/observability/metrics.py").read_text(
        encoding="utf-8"
    )
    # Only the instrument names passed to create_counter/create_histogram — not the
    # meter name, which is never a metric.
    return {
        name.replace(".", "_")
        for name in re.findall(r'create_(?:counter|histogram)\(\s*\n?\s*"([^"]+)"', src)
    }


def test_canary_queries_metrics_the_app_actually_emits() -> None:
    """The AnalysisTemplate must query metric names that exist.

    It used to query `http_requests_total`, which this app has never emitted — there was
    no MeterProvider at all. Zero series, no data, analysis passes, "automated rollback"
    rolls back nothing.
    """
    tpl = ANALYSIS_TEMPLATE.read_text(encoding="utf-8")
    emitted = _emitted_instruments()
    assert emitted, "no instruments parsed from metrics.py — the test itself is broken"

    for promql_metric in set(re.findall(r"\b(anime_[a-z_]+)\{", tpl)):
        assert _base_metric(promql_metric) in emitted, (
            f"canary queries {promql_metric!r}, which the app never emits. "
            f"A PromQL query over zero series returns no data, and no data does NOT fail "
            f"an Argo analysis — the gate would pass every deploy. Emitted: {sorted(emitted)}"
        )


def test_canary_fails_on_empty_result() -> None:
    """ "I could not measure it" must never be read as "it's fine".

    Without a len(result) guard, an empty Prometheus response satisfies the success
    condition vacuously and the canary rubber-stamps the rollout.
    """
    tpl = ANALYSIS_TEMPLATE.read_text(encoding="utf-8")
    conditions = re.findall(r"successCondition:\s*(.+)", tpl)
    assert conditions, "AnalysisTemplate has no successCondition"
    for cond in conditions:
        assert "len(result)" in cond, (
            f"successCondition {cond!r} does not guard against an empty result — "
            "no data would silently PASS the canary"
        )


def test_dashboard_queries_metrics_the_app_actually_emits() -> None:
    """A blank panel and a healthy system look identical. Don't ship queries that can't match."""
    dash = DASHBOARD.read_text(encoding="utf-8")
    emitted = _emitted_instruments()

    for promql_metric in set(re.findall(r"\b(anime_[a-z_]+)[{(\s]", dash)):
        assert _base_metric(promql_metric) in emitted, (
            f"dashboard queries {promql_metric!r}, which the app never emits — "
            f"the panel would render empty forever. Emitted: {sorted(emitted)}"
        )


@pytest.mark.parametrize(
    "key",
    [
        "LLM_PRICING",  # missing -> every call meters at $0.00
        "OTEL_SERVICE_NAME",  # drift -> blank dashboards + dead canary
        "RERANKER_MODEL",  # drift from the baked image -> download at runtime -> timeout
        "QUOTA_FREE_TIER_DAILY",  # the documented limit people trust
        "JWT_LEEWAY_SECONDS",  # 0 -> intermittent 401s on valid tokens
    ],
)
def test_load_bearing_keys_are_documented(key: str) -> None:
    """Every setting whose absence or drift causes a SILENT failure must be in .env.example.

    An undocumented setting with a dangerous default is a trap laid for whoever onboards
    next — and the default is exactly what they'll get.
    """
    assert key in _env_example(), f"{key} is load-bearing but absent from .env.example"


CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


def test_ci_clerk_dummy_key_has_a_valid_shape() -> None:
    """The build-time Clerk key in CI must be a VALID publishable key, not a placeholder.

    A Clerk publishable key is base64 with structure, not an opaque string: Clerk decodes
    it at import and throws on a malformed one, which crashes the prerender of every page
    that uses Clerk. `pk_test_ci_build_only` looks like a perfectly reasonable placeholder
    and fails the web build 100% of the time — CI would have gone red on its very first
    run, on a job whose whole purpose is to be trusted.

    Shape: "pk_test_" + base64("<domain>$").
    """
    import base64

    text = CI_WORKFLOW.read_text(encoding="utf-8")
    keys = re.findall(r"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY[:=]\s*(pk_\S+)", text)
    assert keys, "CI has no NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY — the web build will fail"

    for key in keys:
        assert key.startswith(("pk_test_", "pk_live_")), f"{key!r} is not a Clerk key"
        payload = key.split("_", 2)[2]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            decoded = base64.b64decode(padded).decode("utf-8")
        except Exception as exc:  # pragma: no cover - the assert message is the point
            raise AssertionError(f"{key!r} is not decodable base64: {exc}") from exc
        assert decoded.endswith("$"), (
            f"{key!r} decodes to {decoded!r}, which is not a Clerk key body "
            f"(expected '<domain>$'). Clerk will throw at prerender and the build dies."
        )
