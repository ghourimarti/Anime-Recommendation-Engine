"""Pure-ASGI middlewares.

Why pure ASGI (not BaseHTTPMiddleware): BaseHTTPMiddleware can buffer/break
StreamingResponse, which would silently kill our SSE endpoint. A pure ASGI
middleware only wraps `send` to inject headers — it never touches the response
body, so streaming stays intact.

Three middlewares live here:
  - RequestIDMiddleware: assigns/propagates an X-Request-ID, binds it into
    structlog + the OTel span.
  - ServerTimingMiddleware: emits `X-Server-Ms` from the ContextVar set by
    `anime_api.timing.time_server_work()`. The k6 load harness reads this
    to validate server-side latency NFRs without Langfuse correlation
    (load-test timing harness).
  - MetricsMiddleware: emits the HTTP request counter + duration histogram that
    dashboards and the canary AnalysisTemplate actually query.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from anime_core.observability.metrics import record_http_request
from opentelemetry import trace

from anime_api.timing import server_duration_ms

_HEADER = b"x-request-id"
_SERVER_MS_HEADER = b"x-server-ms"

# Probe endpoints. Kubernetes hits these every few seconds per pod, forever, and
# they tell you nothing about the service's behaviour that the probe result
# doesn't already tell Kubernetes.
#
# Left in, they drown everything else: a real sample showed 93 GET /health spans
# against 3 actual /v1/recommend spans — a 31:1 noise ratio, in which the traces
# you need are needles in a haystack you built yourself. They also skew latency
# histograms (a 1ms health check pulls p50 toward zero) and inflate request
# counts, which is exactly the signal the canary analysis reasons about.
EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics", "/favicon.ico"})


class RequestIDMiddleware:
    """Pure-ASGI middleware: bind a request id into log context + echo it back."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        for key, value in scope.get("headers", []):
            if key == _HEADER:
                request_id = value.decode("latin-1")
                break

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=scope.get("path", ""),
            method=scope.get("method", ""),
        )
        # stamp the request_id onto the OTel span as an attribute
        # so the support flow (request_id from a customer ticket) ALSO works in
        # observability tools that index span attributes (Tempo/Jaeger search).
        span = trace.get_current_span()
        if span.get_span_context().is_valid:
            span.set_attribute("request.id", request_id)

        logger = structlog.get_logger("anime_api.request")
        await logger.ainfo("request.start")

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((_HEADER, request_id.encode("latin-1")))
                await logger.ainfo("request.end", status_code=message["status"])
            await send(message)

        await self.app(scope, receive, send_wrapper)


class MetricsMiddleware:
    """Pure-ASGI middleware: emit the HTTP request counter + duration histogram.

    This is the middleware whose absence made the whole metrics stack decorative.
    The collector, Prometheus and Grafana were all wired up and running — and
    carrying nothing, because no application metric was ever recorded.

    It sits OUTSIDE the routing layer, so `scope["route"]` is only populated by the
    time the response starts. We therefore read the route template in the send
    wrapper, not on the way in.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http" or scope.get("path", "") in EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope.get("method", "UNKNOWN")
        recorded = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal recorded
            if message["type"] == "http.response.start" and not recorded:
                recorded = True
                # The route TEMPLATE, not the raw path: "/v1/anime/{mal_id}", never
                # "/v1/anime/5114". Raw paths turn every id into its own time series
                # and kill the metrics backend by cardinality.
                #
                # A request that matched no route has no scope["route"] — bucket it
                # as a literal "unmatched" rather than emitting the raw path, or a
                # 404 scanner probing random URLs becomes an unbounded cardinality
                # attack on our own monitoring.
                route_obj = scope.get("route")
                route = getattr(route_obj, "path", None) or "unmatched"
                record_http_request(
                    route=route,
                    method=method,
                    status_code=message["status"],
                    duration_s=time.perf_counter() - start,
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # An unhandled exception never reaches http.response.start, so without
            # this the request would be counted... nowhere. A 500 that vanishes from
            # the metrics is the single worst thing that can happen to an error-rate
            # alert — the error budget looks perfect precisely when it's on fire.
            if not recorded:
                recorded = True
                route_obj = scope.get("route")
                record_http_request(
                    route=getattr(route_obj, "path", None) or "unmatched",
                    method=method,
                    status_code=500,
                    duration_s=time.perf_counter() - start,
                )
            raise


class ServerTimingMiddleware:
    """Pure-ASGI middleware: emits X-Server-Ms when a route timed its work.

    A handler that called `time_server_work()` stashed a duration in the
    `server_duration_ms` ContextVar. We reset the var at request start (so a
    previous request's value can't leak across) and append the header at
    response start if it was set during this request.

    Routes that don't time their work emit no header — k6 scenarios that
    expect the header check its presence before reporting to the Trend.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Reset so a prior request's value can't leak across to this one.
        # ContextVars are task-local in asyncio, but explicit reset is cheap
        # insurance against unexpected execution contexts.
        token = server_duration_ms.set(None)

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                duration = server_duration_ms.get()
                if duration is not None:
                    headers = message.setdefault("headers", [])
                    headers.append((_SERVER_MS_HEADER, f"{duration:.1f}".encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            server_duration_ms.reset(token)
