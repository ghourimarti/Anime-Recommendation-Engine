"""OpenTelemetry SDK setup + auto-instrumentations.

A global TracerProvider AND a global MeterProvider, established at app startup,
exporting via OTLP gRPC to whatever backend is on the other end (Grafana Tempo,
Honeycomb, Datadog OTel endpoint, …). We use portable (vendor-neutral)
instrumentation: this module is the only place that knows about the OTel SDK;
everything else just calls `opentelemetry.trace.get_tracer(__name__)` /
`opentelemetry.metrics.get_meter(__name__)` and gets the configured provider.

The MeterProvider was missing for a long time, and its absence was invisible in a
specific and dangerous way. The OTel metrics API is a no-op when no SDK provider
is installed — by design, so libraries can instrument freely. So every
`counter.add()` in the codebase ran, cost nothing, and recorded nothing. The
collector had a metrics pipeline, Prometheus scraped it, Grafana queried it, and
the whole chain was live and empty. Worse, the canary AnalysisTemplate gated
rollouts on a metric with zero series: a PromQL query over no data returns no
result, the analysis never fails, and the "automated rollback" silently passes
every deploy. Dashboards that show nothing look identical to systems that are
behaving.

Auto-instrumentations cover the obvious surfaces:
  - FastAPI       → HTTP server spans (one per request)
  - SQLAlchemy    → DB query spans (lit up with statement text)
  - Redis         → cache op spans
  - HTTPX         → outbound HTTP spans (Groq + OpenAI calls land here)

The FastAPI instrumentation needs the app instance, so it lives in a separate
`instrument_fastapi(app)` call invoked from `main.py` AFTER `FastAPI()` runs.

Idempotency: `_CONFIGURED` guards repeated setup_otel() calls — tests can call
it from a fixture and from `create_app()` without double-instrumenting.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

logger = logging.getLogger(__name__)

_CONFIGURED = False

# How often the SDK pushes metrics to the collector. 15s is a deliberate pick: it
# is half the usual 30s Prometheus scrape, so every scrape sees a fresh export
# (Nyquist, basically). Longer and the canary analysis reasons over stale windows;
# much shorter and you pay export overhead for data nobody reads.
METRIC_EXPORT_INTERVAL_MS = int(os.environ.get("OTEL_METRIC_EXPORT_INTERVAL_MS", "15000"))

# Paths that emit NO span. Comma-separated (the instrumentor's own format), and
# matched as regexes against the path. Kept in sync with EXCLUDED_PATHS in
# anime_api.middleware, which does the same for metrics.
DEFAULT_EXCLUDED_URLS = "health,ready,metrics,favicon.ico"

# Histogram buckets for request duration, in SECONDS.
#
# This view is load-bearing. OTel's default bucket boundaries are
# [0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000] — a
# scale that only makes sense for MILLISECONDS. Our durations are seconds (the OTel
# spec is explicit about that), so with the defaults *every* real request lands in
# the very first bucket: measured, a 2.5s recommend call and a 0.1ms health check
# were indistinguishable, both "<= 5".
#
# A p95 computed from that says "somewhere between 0 and 5 seconds", which is not a
# latency SLO, it's a shrug. And it fails silently: the dashboard renders a
# confident line, the alert never fires, and the number is meaningless.
#
# These boundaries are the Prometheus client defaults, extended at the top end
# because a RAG request legitimately takes seconds — with buckets straddling the
# p95 SLO, so the quantile is actually interpolated from real resolution.
DURATION_BUCKETS_SECONDS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75,
    1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0,
)  # fmt: skip

# Retrieval confidence is a PROBABILITY in (0, 1), so the seconds buckets above are
# just as wrong for it as the millisecond defaults are for durations — and worse,
# because every possible value is <= 1 and would land in the first default bucket
# ("<= 5"). Measured before fixing: two real requests, both reported only as
# "<= 5.0", from which the dashboard's percentile panels and the routing-threshold
# comparison could say nothing at all.
#
# The boundaries are tight around 0.731 — the sigmoid of the routing threshold
# (logit 1.0) — because the question this histogram answers is "how far is live
# traffic from the routing cutoff", and that needs resolution exactly there.
CONFIDENCE_BUCKETS = (
    0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7,
    0.731, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99,
)  # fmt: skip

_VIEWS = (
    View(
        instrument_name="anime.http.duration",
        aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS_SECONDS),
    ),
    # Same seconds scale as the request duration: retrieval stages run from a
    # sub-millisecond MMR to a multi-second cross-encoder, and the whole point of
    # the panel is telling those apart.
    View(
        instrument_name="anime.retrieval.stage.duration",
        aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS_SECONDS),
    ),
    View(
        instrument_name="anime.retrieval.confidence",
        aggregation=ExplicitBucketHistogramAggregation(CONFIDENCE_BUCKETS),
    ),
)


def setup_otel(
    *,
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
    exporter: SpanExporter | None = None,
    metric_exporter: MetricExporter | None = None,
) -> TracerProvider:
    """Initialise OTel — exporters, tracer + meter providers, global instrumentations.

    Args:
        service_name:    `service.name` resource attribute. Falls back to env
                         OTEL_SERVICE_NAME, then to "anime-api".
        otlp_endpoint:   OTLP gRPC endpoint. Falls back to env
                         OTEL_EXPORTER_OTLP_ENDPOINT. When neither is set AND no
                         explicit exporter is provided, falls through to the
                         Console exporters (dev) — never silently drops telemetry.
        exporter:        Inject a custom span exporter (tests use InMemorySpanExporter).
        metric_exporter: Inject a custom metric exporter (tests use InMemoryMetricReader).
    """
    global _CONFIGURED

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "anime-api")
    resource = Resource.create({"service.name": name, "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)

    # OTel-standard opt-out: if OTEL_SDK_DISABLED=true, configure providers
    # WITHOUT any exporter (telemetry is dropped instead of exported). Tests set
    # this; prod doesn't. Avoids tests hammering localhost:4317 when no
    # collector is running.
    disabled = os.environ.get("OTEL_SDK_DISABLED", "").lower() in {"true", "1"}
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not disabled:
        if exporter is not None:
            chosen: SpanExporter = exporter
        elif endpoint:
            chosen = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True,  # local dev collector; TLS belongs in K8s service-mesh layer
            )
        else:
            # Better than silently dropping: print to stdout so the dev SEES traces.
            chosen = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(chosen))

    trace.set_tracer_provider(provider)

    # ── metrics ──────────────────────────────────────────────────────────────
    # Without this block every instrument in anime_core.observability.metrics is a
    # no-op: the OTel metrics API silently does nothing until an SDK MeterProvider
    # is installed. Installing it here is what turns all those existing call sites
    # into actual time series — no changes needed at any of them.
    if disabled:
        # No readers: the instruments stay valid and callable, they just record
        # into a provider that exports nowhere.
        metrics.set_meter_provider(MeterProvider(resource=resource, views=_VIEWS))
    else:
        if metric_exporter is not None:
            chosen_metric: MetricExporter = metric_exporter
        elif endpoint:
            chosen_metric = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        else:
            chosen_metric = ConsoleMetricExporter()
        reader = PeriodicExportingMetricReader(
            chosen_metric, export_interval_millis=METRIC_EXPORT_INTERVAL_MS
        )
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=[reader], views=_VIEWS)
        )

    # Global auto-instrumentations — idempotent on their own, but the
    # _CONFIGURED guard means we only re-register on a fresh call. Also skipped
    # when the SDK is disabled (no point patching libs that won't emit anyway).
    if not _CONFIGURED and not disabled:
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        _CONFIGURED = True

    return provider


def instrument_fastapi(app: Any, *, excluded_urls: str | None = None) -> None:
    """Attach the FastAPI auto-instrumentation to an app instance.

    Lives separately from setup_otel() because FastAPI's instrumentor needs the
    app object, which doesn't exist until create_app() runs.

    excluded_urls: comma-separated patterns that emit NO span. Health probes belong
    here. Kubernetes hits /health and /ready every few seconds per pod, forever,
    and a span for each is pure cost: a real sample showed 93 GET /health spans
    against 3 /v1/recommend spans. That is a 31:1 noise ratio in the exact tool you
    reach for when something is broken, and you pay to ingest and store every one
    of them. The probe's job is to answer Kubernetes, not to narrate itself.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=excluded_urls or os.environ.get("OTEL_EXCLUDED_URLS", DEFAULT_EXCLUDED_URLS),
    )


def reset_for_tests() -> None:
    """Test-only: reset state so a fresh setup_otel() installs new providers.

    Touches OTel's private once-flags for the global Tracer AND Meter providers —
    the SDK enforces "set once" by design, but tests routinely need to re-set.
    Stable across OTel SDK versions since 1.18+; treat as a stable test seam.

    The meter half matters as much as the tracer half: without it, the first test
    to install a MeterProvider wins for the whole session and every later test
    silently measures the wrong one.
    """
    global _CONFIGURED
    _CONFIGURED = False

    try:
        import opentelemetry.trace as trace_mod

        # Force the OTel internal "set once" guard back to its un-set state.
        trace_mod._TRACER_PROVIDER = None
        once = trace_mod._TRACER_PROVIDER_SET_ONCE
        if hasattr(once, "_done"):
            once._done = False
    except Exception:
        pass

    try:
        # The metrics globals live in the _internal module; `opentelemetry.metrics`
        # only re-exports the functions, so reach for the module that owns them.
        from opentelemetry.metrics import _internal as metrics_internal

        # SHUT THE OLD PROVIDER DOWN before dropping the reference. A MeterProvider
        # owns a PeriodicExportingMetricReader, and that reader owns a background
        # thread that keeps exporting on its interval. Just repointing the global
        # leaves that thread alive: it outlives the test, and eventually writes into
        # a stdout pytest has already closed. Unlike a TracerProvider (which exports
        # on flush), a metrics provider is a live thing that has to be stopped.
        old = metrics_internal._METER_PROVIDER
        if old is not None and hasattr(old, "shutdown"):
            with contextlib.suppress(Exception):
                old.shutdown()

        metrics_internal._METER_PROVIDER = None
        once_m = metrics_internal._METER_PROVIDER_SET_ONCE
        if hasattr(once_m, "_done"):
            once_m._done = False
    except Exception:
        pass
