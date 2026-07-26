"""Structured (JSON) logging via structlog — the foundation of the observability layer.

Processor chain (order matters):
  1. merge_contextvars     — pull in request_id/path/method from the middleware
  2. add_log_level         — "info" / "warning" / etc.
  3. add_logger_name       — which module emitted the line
  4. TimeStamper(utc=True) — ISO-8601, UTC; the only sane choice for distributed logs
  5. bind_otel_trace       — splice in trace_id/span_id from the active OTel span
  6. redact_processor      — mask PII keys (email, query, password, …) BEFORE serialize
  7. JSONRenderer          — final serialization to a single line of JSON

Putting the renderer last is critical: every processor before it operates on a
dict (cheap, structured). Redaction must run on the DICT — regex on serialized
JSON is the canonical wrong move.

stdlib `logging` is wired to forward through the same chain so any library that
uses `logging.getLogger()` (sqlalchemy, langchain, uvicorn, …) ends up in our
JSON pipe with the same redaction and trace correlation.
"""

from __future__ import annotations

import logging
from typing import IO, Any

import structlog

from anime_core.observability.redaction import redact_processor
from anime_core.observability.trace_context import bind_otel_trace


def _shared_processors() -> list[Any]:
    """The processor chain used by BOTH structlog-native and stdlib loggers."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        bind_otel_trace,
        redact_processor,
    ]


def configure_logging(level: str = "INFO", stream: IO[str] | None = None) -> None:
    """Configure structlog + stdlib logging to emit JSON at the given level.

    Idempotent: safe to call from create_app() AND from pytest fixtures.

    Args:
        level:  log level name ("INFO", "DEBUG", ...).
        stream: where the StreamHandler writes. Defaults to sys.stderr.
                Tests inject an io.StringIO() to capture output deterministically
                without pytest's capsys/capfd intercepting (pytest's logging
                plugin can swallow handler output, even at FD level).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib `logging` first — structlog will use its LoggerFactory
    # to delegate to stdlib loggers (which DO have a `.name`, so add_logger_name
    # works). Without this delegation, structlog.stdlib.* processors fail.
    stdlib_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=_shared_processors(),
    )
    handler = logging.StreamHandler(stream) if stream is not None else logging.StreamHandler()
    handler.setFormatter(stdlib_formatter)
    root = logging.getLogger()
    # Replace any prior handlers (defensive on repeated configure_logging calls).
    root.handlers = [handler]
    root.setLevel(log_level)

    structlog.configure(
        processors=[
            *_shared_processors(),
            # Wrap the event for the stdlib ProcessorFormatter to hand back to
            # the JSONRenderer (otherwise structlog renders early + we double-encode).
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "anime") -> Any:
    """Return a bound structlog logger. `Any` return type avoids leaking the
    structlog-stdlib hybrid into call sites that just want `.info()`."""
    return structlog.get_logger(name)
