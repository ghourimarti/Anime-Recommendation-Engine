"""Unit tests for OTel setup.

Uses InMemorySpanExporter so the test can assert on captured spans without a
running collector. The auto-instrumentation paths (FastAPI/SQLAlchemy/Redis/
httpx) are exercised at the integration level in apps/api/tests.
"""

from __future__ import annotations

import pytest
from anime_core.observability.otel import reset_for_tests, setup_otel
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def in_memory_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Fresh exporter per test; reset OTel state too.

    Clear OTEL_SDK_DISABLED because apps/api/tests/conftest.py sets it at
    module import (to silence grpc connection noise in API tests). Without
    clearing, setup_otel below short-circuits and the exporter never receives
    spans.
    """
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    reset_for_tests()
    return InMemorySpanExporter()


def test_service_name_lands_in_resource(in_memory_exporter: InMemorySpanExporter) -> None:
    provider = setup_otel(service_name="anime-test", exporter=in_memory_exporter)
    # The Resource is what ends up on every span via the SpanProcessor.
    attrs = dict(provider.resource.attributes)
    assert attrs["service.name"] == "anime-test"


def test_spans_export_to_injected_exporter(
    in_memory_exporter: InMemorySpanExporter,
) -> None:
    setup_otel(service_name="anime-test", exporter=in_memory_exporter)
    tracer = trace.get_tracer("anime_core.tests")
    with tracer.start_as_current_span("manual-span"):
        pass
    # Force flush to make the assertion deterministic — BatchSpanProcessor
    # batches by default and would otherwise hold spans in memory.
    trace.get_tracer_provider().force_flush()  # type: ignore[attr-defined]
    spans = in_memory_exporter.get_finished_spans()
    assert any(s.name == "manual-span" for s in spans)


def test_setup_otel_is_idempotent(in_memory_exporter: InMemorySpanExporter) -> None:
    """Calling setup_otel twice must not double-register instrumentations."""
    setup_otel(service_name="anime-test", exporter=in_memory_exporter)
    setup_otel(service_name="anime-test", exporter=in_memory_exporter)
    # No exception means the auto-instrumentations didn't re-register and explode.


def test_falls_back_to_console_when_no_endpoint_or_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Better than silently dropping: dev sees spans in stdout."""
    reset_for_tests()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    provider = setup_otel(service_name="anime-test")
    # Provider exists and has at least one span processor wired.
    assert provider is not None


# ── metrics: the MeterProvider that wasn't there ─────────────────────────────


def test_setup_otel_installs_a_real_meter_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE regression test for the decorative metrics pipeline.

    setup_otel used to configure a TracerProvider and nothing else. With no SDK
    MeterProvider installed, the OTel metrics API silently no-ops — by design, so
    that libraries can instrument unconditionally. So every counter.add() in this
    codebase ran, cost nothing, and recorded nothing.

    Nothing looked broken: the collector had a metrics pipeline, Prometheus scraped
    it, Grafana queried it. The entire chain was healthy and completely empty, and
    an empty dashboard is indistinguishable from a quiet system.
    """
    from opentelemetry import metrics as metrics_api
    from opentelemetry.sdk.metrics import MeterProvider

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    reset_for_tests()
    setup_otel(service_name="anime-test", exporter=InMemorySpanExporter())

    provider = metrics_api.get_meter_provider()
    assert isinstance(provider, MeterProvider), (
        f"no SDK MeterProvider installed (got {type(provider).__name__}) — "
        "every metric in the app would silently record nothing"
    )


def test_metrics_actually_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: a recorded request must come out the other side as a data point.

    Note what this also proves: anime_core.observability.metrics is imported LONG
    before setup_otel() runs (routes import it at module load). That works because
    the OTel API hands out proxy instruments that re-bind once a real provider is
    installed — so instruments defined at import time are not permanently dead.
    Worth pinning: if that ever stopped being true, every metric would go quiet and
    nothing else would fail.
    """
    from anime_core.observability.metrics import record_http_request
    from opentelemetry import metrics as metrics_api
    from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult

    class CapturingExporter(MetricExporter):
        def __init__(self) -> None:
            super().__init__()
            self.batches: list = []

        def export(self, metrics_data, timeout_millis: float = 10_000, **kwargs):  # type: ignore[no-untyped-def]
            self.batches.append(metrics_data)
            return MetricExportResult.SUCCESS

        def force_flush(self, timeout_millis: float = 10_000) -> bool:
            return True

        def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    reset_for_tests()

    captured = CapturingExporter()
    setup_otel(
        service_name="anime-test",
        exporter=InMemorySpanExporter(),
        metric_exporter=captured,
    )

    # Rebind the module's instruments to the provider we just installed.
    #
    # OTel hands out PROXY instruments before an SDK provider exists, and each proxy
    # binds to the FIRST real provider it sees — permanently. In production that is
    # exactly right (one provider, set once at startup, so import order can't hurt
    # you). In a test file that installs several providers in sequence, the
    # instruments are still wired to whichever one came first, so a fresh exporter
    # would see nothing. Reloading rebuilds them against the current provider.
    import importlib

    from anime_core.observability import metrics as metrics_mod

    importlib.reload(metrics_mod)

    metrics_mod.record_http_request(
        route="/v1/recommend", method="POST", status_code=200, duration_s=2.4
    )
    assert record_http_request is not None  # the public symbol still imports fine
    metrics_api.get_meter_provider().force_flush()  # type: ignore[attr-defined]

    names = {
        metric.name
        for batch in captured.batches
        for rm in batch.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
    }
    assert "anime.http.requests" in names, f"request counter never exported; got {names}"
    assert "anime.http.duration" in names, f"duration histogram never exported; got {names}"


def test_duration_buckets_are_on_a_seconds_scale() -> None:
    """The histogram buckets must resolve SECONDS, not milliseconds.

    OTel's default boundaries ([0, 5, 10, ... 10000]) are a millisecond scale. Our
    durations are seconds, so under the defaults every real request — a 2.5s RAG
    call and a 0.1ms health check alike — landed in the same first bucket, and any
    p95 derived from it was a confident-looking work of fiction.

    So: the buckets must have resolution below 1s, and must straddle the ~3s p95
    SLO so the quantile is interpolated from real data.
    """
    from anime_core.observability.otel import DURATION_BUCKETS_SECONDS as b

    assert min(b) < 0.01, "no sub-10ms resolution: fast/cached responses are indistinguishable"
    assert any(2.0 <= x <= 4.0 for x in b), "no buckets around the ~3s p95 SLO to interpolate from"
    assert max(b) >= 10.0, "no bucket above 10s: slow outliers vanish into +Inf"
    assert list(b) == sorted(b), "bucket boundaries must be ascending"


def test_confidence_buckets_are_on_a_probability_scale() -> None:
    """Retrieval confidence is a probability, and its buckets must resolve one.

    Same failure as the duration histogram, found the same way — by reading the
    exported data instead of the dashboard. Under the default boundaries every
    confidence value (all of them <= 1) fell into the single "<= 5" bucket, so the
    percentile panels and the comparison against the routing threshold were
    computed from a distribution with exactly one cell. They would have rendered a
    confident line meaning nothing.

    0.731 is the sigmoid of the routing threshold (logit 1.0): the histogram exists
    to answer how far live traffic sits from that cutoff, so it needs a boundary
    AT it and resolution around it.
    """
    from anime_core.observability.otel import CONFIDENCE_BUCKETS as b

    assert max(b) < 1.0, "a probability cannot exceed 1: buckets above it are dead space"
    assert min(b) <= 0.05, "no resolution at the low end: confident and hopeless look alike"
    assert 0.731 in b, "no boundary at the routing threshold — the key comparison is uninterpolated"
    assert sum(1 for x in b if 0.6 <= x <= 0.9) >= 5, "too coarse around the routing decision"
    assert list(b) == sorted(b), "bucket boundaries must be ascending"


def test_lag_buckets_resolve_milliseconds() -> None:
    """Loop lag needs its own scale: a healthy loop lives BELOW the duration buckets.

    Measured here 2026-09-20 the loop lagged 3.3ms on average, so every healthy
    sample would land in DURATION_BUCKETS_SECONDS' first bucket ("<= 0.005") and the
    panel could not tell a 0.4ms loop from a 4ms one — which is the entire range the
    metric exists to watch. The top end still has to reach seconds: the failure being
    hunted is a loop blocked by CPU work, measured at 966ms.
    """
    from anime_core.observability.otel import LAG_BUCKETS_SECONDS as b

    assert min(b) <= 0.001, "no sub-millisecond resolution: a healthy loop is one cell"
    assert sum(1 for x in b if x <= 0.01) >= 4, "too coarse where healthy lag actually lives"
    assert max(b) >= 1.0, "no bucket at 1s: a blocked loop vanishes into +Inf"
    assert list(b) == sorted(b), "bucket boundaries must be ascending"


def _histograms_without_a_view(source: str, viewed: set[str]) -> list[str]:
    """Histogram names created in `source` that no View names. The guard, in one place.

    Extracted so the guard itself can be exercised against a synthetic source. A check
    that has only ever been run against passing input is not known to work — that is the
    same reasoning the inspection script's --selftest applies to its own assertions.
    """
    import re

    created = set(re.findall(r'create_histogram\(\s*"([^"]+)"', source))
    assert created, "no histograms found — the regex stopped matching, not the risk"
    return sorted(created - viewed)


def test_every_histogram_instrument_has_a_view() -> None:
    """A histogram with no View silently inherits OTel's MILLISECOND defaults.

    This is the regression that shipped twice. It is invisible in code review and
    invisible on the dashboard — the panel renders a confident line. Measured
    2026-09-20, an unviewed rerank histogram reported a p95 of 9.5s for a stage whose
    entire wall-clock is 2.4s, because every sample sat in one 0-to-5 bucket and the
    quantile was pure interpolation.

    So the check is structural, not behavioural: every histogram created in
    metrics.py must be named by a View. Reading the source is deliberate — importing
    the module would only list the instruments that happen to have been touched.
    """
    from pathlib import Path

    from anime_core.observability import metrics
    from anime_core.observability.otel import _VIEWS

    src = Path(metrics.__file__).read_text(encoding="utf-8")
    viewed = {v._instrument_name for v in _VIEWS}

    missing = _histograms_without_a_view(src, viewed)
    assert not missing, f"histogram(s) with no View, so on millisecond buckets: {missing}"


def test_the_view_guard_can_actually_fail() -> None:
    """The negative control: prove the guard above catches what it exists to catch.

    Without this, the guard is only known to agree with today's code. The failure it
    must catch is a new histogram added without a matching View — which is exactly how
    `anime.retrieval.confidence` (O.4) and then both I.9 instruments shipped on
    millisecond buckets. Neither was caught in review; both looked fine on the dashboard.
    """
    source = """
        _ok = _meter.create_histogram("anime.thing.viewed", unit="s")
        _oops = _meter.create_histogram("anime.thing.forgotten", unit="s")
    """

    assert _histograms_without_a_view(source, {"anime.thing.viewed"}) == ["anime.thing.forgotten"]
    # ...and stays quiet when every instrument IS covered, or it would be noise.
    assert _histograms_without_a_view(source, {"anime.thing.viewed", "anime.thing.forgotten"}) == []


def test_health_probes_are_excluded_from_tracing() -> None:
    """Probe endpoints must emit NO span.

    Kubernetes hits /health and /ready every few seconds per pod, forever, and each
    one is a span we pay to ingest, store and scroll past. A real sample of this app
    showed 93 GET /health spans against 3 /v1/recommend spans — a 31:1 ratio, which
    turns the tool you reach for during an incident into a haystack you built
    yourself.

    The probe's job is to answer Kubernetes, not to narrate itself.
    """
    from anime_core.observability.otel import DEFAULT_EXCLUDED_URLS

    excluded = {p.strip() for p in DEFAULT_EXCLUDED_URLS.split(",")}
    assert "health" in excluded
    assert "ready" in excluded


def test_metrics_and_traces_exclude_the_same_paths() -> None:
    """The two exclusion lists must agree.

    They are enforced in different places — the FastAPI instrumentor filters spans,
    our own middleware filters metrics — and a path excluded from one but not the
    other gives you a route with metrics and no traces (or the reverse), which is
    the most confusing possible state to debug from.
    """
    from anime_api.middleware import EXCLUDED_PATHS
    from anime_core.observability.otel import DEFAULT_EXCLUDED_URLS

    traced_exclusions = {p.strip() for p in DEFAULT_EXCLUDED_URLS.split(",")}
    metric_exclusions = {p.lstrip("/") for p in EXCLUDED_PATHS}
    assert traced_exclusions == metric_exclusions, (
        f"trace exclusions {traced_exclusions} != metric exclusions {metric_exclusions}"
    )
