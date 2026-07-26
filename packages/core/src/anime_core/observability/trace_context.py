"""Bridge structlog ↔ OpenTelemetry: bind the active span's trace_id/span_id
to every log record produced inside the request.

The linchpin of cross-system correlation. Without it:
  - Logs go to Loki / CloudWatch.
  - Traces go to Tempo / Jaeger.
  - LLM traces go to Langfuse.
  - You have THREE incompatible debugging surfaces. Welcome to a 4-hour incident.

With it: every log line carries the same hex trace_id as the OTel span, and the
Langfuse trace can carry it too — so the SUPPORT VIEW (request_id from header)
and the INCIDENT VIEW (trace_id from an alert) both lead to the same record.

The processor is a no-op when no span is active (e.g. background jobs that
haven't been instrumented yet) — we deliberately DO NOT fake "0000…" trace ids,
because that pollutes search filters in observability tools.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace


def bind_otel_trace(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor — add trace_id/span_id from the active OTel span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        # No active span (e.g. process startup, background task before
        # instrumentation runs). DO NOT add fake IDs — search filters will hate them.
        return event_dict
    event_dict["trace_id"] = format(ctx.trace_id, "032x")
    event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
