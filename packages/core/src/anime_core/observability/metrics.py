"""Application metrics — the instruments, defined once, recorded from anywhere.

This module only touches the OpenTelemetry metrics *API*, never the SDK. That
separation is deliberate and is what makes it safe to call `record_*()` from
library code: with no MeterProvider installed, every instrument is a no-op that
costs a few nanoseconds and records nothing. The moment `configure_otel()`
installs the SDK MeterProvider, the exact same call sites start exporting — no
conditionals, no import-order traps, no "is telemetry on?" checks scattered
through business logic.

Metric naming follows OTel semantic conventions: `<domain>.<thing>.<unit>`,
counters as totals, durations in seconds (not ms — the spec is explicit, and
Prometheus histogram buckets assume it).

Cardinality is the thing that kills a metrics backend, so every attribute here is
bounded by construction: model names, route templates, and enum-ish outcomes.
Never attach a user id, a query string, or a trace id as a metric attribute —
those are trace/log territory, and they will multiply your time series until the
backend falls over.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.util.types import Attributes

_meter = metrics.get_meter("anime.app")

# ── HTTP server ──────────────────────────────────────────────────────────────
# These are what the canary analysis gates on, so they have to exist and they have
# to be named the same thing the AnalysisTemplate queries. A PromQL query against
# a metric with zero series returns no data — and "no data" does not fail an
# Argo Rollouts analysis, it just... passes. That is how an "automated rollback"
# ends up rubber-stamping every deploy.
_http_requests = _meter.create_counter(
    "anime.http.requests",
    unit="1",
    description="HTTP requests by route, method and status class.",
)
_http_duration = _meter.create_histogram(
    "anime.http.duration",
    unit="s",
    description="HTTP request duration in seconds (OTel convention: seconds, not ms).",
)


def record_http_request(*, route: str, method: str, status_code: int, duration_s: float) -> None:
    """Record one served HTTP request.

    `route` MUST be the route TEMPLATE ("/v1/anime/{mal_id}"), never the raw path.
    A raw path makes every distinct id its own time series, and a metrics backend
    dies of cardinality long before it dies of volume.

    status_class ("2xx"/"5xx") is what alerts and canary analysis actually query —
    the exact code is kept alongside it because when you're debugging you want to
    know it was a 429 and not a 404, and status codes are a small bounded set.
    """
    attrs: Attributes = {
        "route": route,
        "method": method,
        "status_code": status_code,
        "status_class": f"{status_code // 100}xx",
    }
    _http_requests.add(1, attrs)
    _http_duration.record(duration_s, attrs)


# ── LLM / cost ───────────────────────────────────────────────────────────────
_llm_calls = _meter.create_counter(
    "anime.llm.calls",
    unit="1",
    description="LLM invocations, by model and outcome.",
)
_llm_tokens = _meter.create_counter(
    "anime.llm.tokens",
    unit="1",
    description="Tokens consumed, by model and direction (input/output).",
)
_llm_cost = _meter.create_counter(
    "anime.llm.cost.usd",
    # unit is intentionally "1", not "USD". The OTel→Prometheus translation appends
    # the unit to the metric name, so unit="USD" on a metric already named ...cost.usd
    # exports as `anime_llm_cost_usd_USD_total` — the currency twice, once shouting.
    # Prometheus convention is that the NAME carries the unit, so the name does it.
    unit="1",
    description="Metered LLM spend in USD, by model.",
)
_llm_unpriced = _meter.create_counter(
    "anime.llm.unpriced.calls",
    unit="1",
    description=(
        "LLM calls billed by the provider but metered at $0 because the model is "
        "absent from LLM_PRICING. Any non-zero value means cost is leaking "
        "unattributed — alert on it."
    ),
)


def record_llm_call(*, model: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """Record one priced LLM call: its tokens and its cost."""
    _llm_calls.add(1, {"model": model, "outcome": "priced"})
    _llm_tokens.add(input_tokens, {"model": model, "direction": "input"})
    _llm_tokens.add(output_tokens, {"model": model, "direction": "output"})
    _llm_cost.add(cost_usd, {"model": model})


def record_unpriced_llm_call(*, model: str) -> None:
    """Record an LLM call we could not price. This is a billing hole, not a warning."""
    _llm_calls.add(1, {"model": model, "outcome": "unpriced"})
    _llm_unpriced.add(1, {"model": model})


_refusals = _meter.create_counter(
    "anime.llm.refusals",
    unit="1",
    description=(
        "Requests the model declined (out-of-scope, or nothing genuinely matched). "
        "Healthy behaviour, not an error — but watch the RATE: a spike means either "
        "an abuse wave or a retrieval regression starving the model of good candidates."
    ),
)


def record_refusal() -> None:
    """Record an honest refusal. Not a failure — the alternative is a confident lie."""
    _refusals.add(1)


# ── worker / queue ───────────────────────────────────────────────────────────
_jobs_processed = _meter.create_counter(
    "anime.worker.jobs",
    unit="1",
    description="Jobs consumed, by queue and outcome (processed/duplicate/failed/poison).",
)
_poison_messages = _meter.create_counter(
    "anime.worker.poison.messages",
    unit="1",
    description=(
        "Messages that could not be parsed and were sent straight to the DLQ. "
        "These once crash-looped the worker; a spike means a producer is emitting "
        "a shape this consumer cannot read."
    ),
)


def record_job(*, queue: str, outcome: str) -> None:
    """Record one job's terminal outcome."""
    _jobs_processed.add(1, {"queue": queue, "outcome": outcome})


def record_poison_message(*, queue: str) -> None:
    """Record an unparseable message. Alert on any sustained non-zero rate."""
    _poison_messages.add(1, {"queue": queue})
