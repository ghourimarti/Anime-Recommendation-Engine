"""Observability package — structlog + OpenTelemetry + Langfuse + PII redaction.

The observability layer lives here. Three concerns, one stable import path:
  - structured logging with PII redaction      (logging.configure_logging)
  - OpenTelemetry SDK setup + auto-instruments (otel.setup_otel)
  - Langfuse callback handler factory          (langfuse_callback.get_langfuse_handler)

Callers import everything from `anime_core.observability` directly, so internal
restructures don't ripple into the API layer.
"""

from __future__ import annotations

from anime_core.observability.langfuse_callback import (
    get_langfuse_handler,
    shutdown_langfuse,
)
from anime_core.observability.logging import configure_logging, get_logger
from anime_core.observability.otel import setup_otel
from anime_core.observability.redaction import DENY_KEYS, REDACTED, redact

__all__ = [
    "DENY_KEYS",
    "REDACTED",
    "configure_logging",
    "get_langfuse_handler",
    "get_logger",
    "redact",
    "setup_otel",
    "shutdown_langfuse",
]
