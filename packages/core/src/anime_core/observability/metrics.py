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

import math

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


# ── self-hosted venue routing (D4b) ──────────────────────────────────────────
# The venue falls through to the hosted chain on any failure, which means it can
# be completely broken while the product looks fine. That exact failure mode has
# already bitten this system twice: the OpenAI fallback silently carried ~50% of
# traffic while masking Groq's tool-call bug, and a working rerank fallback hid a
# 37x tail-latency problem. A resilience mechanism that works perfectly is also a
# mechanism that hides what it is compensating for. So: measure the fall-throughs.
_venue_decisions = _meter.create_counter(
    "anime.llm.venue.decisions",
    unit="1",
    description=(
        "Venue routing outcomes. decision=hosted (confidence below threshold, the "
        "normal majority), venue_served (self-hosted answered), venue_fallback_error "
        "(venue raised), venue_fallback_empty (venue returned nothing usable). "
        "ALERT ON: venue_fallback_* / (venue_served + venue_fallback_*) rising — the "
        "venue is degrading and the hosted chain is quietly absorbing the cost."
    ),
)
_retrieval_confidence = _meter.create_histogram(
    "anime.retrieval.confidence",
    unit="1",
    description=(
        "Top-1 rerank relevance at routing time, as a 0-1 probability — sigmoid of "
        "the raw cross-encoder logit (see record_retrieval_confidence for why it is "
        "not the raw logit). The routing threshold is 1.0 in LOGIT space, which is "
        "0.731 here. The threshold was derived from the golden set, which is curated "
        "and is NOT production traffic; this histogram is how you find out the live "
        "distribution has drifted from the measured one, at which point the threshold "
        "needs re-deriving rather than nudging. Absent when the reranker timed out."
    ),
)


def record_venue_decision(*, decision: str) -> None:
    """Record one venue routing outcome. See _venue_decisions for the alert."""
    _venue_decisions.add(1, {"decision": decision})


def record_retrieval_confidence(logit: float) -> None:
    """Record the routing signal, converted to a 0-1 probability.

    WHY NOT THE RAW LOGIT. The first version recorded the cross-encoder score
    directly and silently recorded NOTHING for most queries: OTel histograms
    reject negative values, and these logits run roughly -11 to +7, so the
    majority are negative. The SDK logs one warning per rejected record and
    drops it - a metric that looks wired up and is quietly empty for exactly
    the population you most want to see.

    Sigmoid is the principled fix rather than an offset hack: it is the
    probability the cross-encoder is actually expressing, it is monotonic in the
    logit (so distribution SHAPE and all percentile comparisons are preserved),
    and it is bounded in (0, 1), which is well-behaved for histogram buckets.

    Routing still compares the RAW logit against the raw threshold - this
    conversion is for the metric only, so the routing decision is never
    mediated by a lossy transform.
    """
    _retrieval_confidence.record(1.0 / (1.0 + math.exp(-logit)))


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
