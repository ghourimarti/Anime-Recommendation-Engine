"""Unit tests for the structlog config.

We inject a StringIO stream into configure_logging() to capture the rendered
JSON deterministically. pytest's logging plugin reliably swallows FD-level
output for plain capsys/capfd fixtures, so DI is the cleaner test seam.
"""

from __future__ import annotations

import io
import json
import logging

import pytest
import structlog
from anime_core.observability.logging import configure_logging, get_logger
from anime_core.observability.redaction import REDACTED


@pytest.fixture
def log_stream() -> io.StringIO:
    """Fresh stream + clean structlog config per test."""
    buf = io.StringIO()
    configure_logging("INFO", stream=buf)
    structlog.contextvars.clear_contextvars()
    return buf


def _parse(buf: io.StringIO) -> dict[str, object]:
    """Return the last JSON-shaped line emitted to the stream."""
    text = buf.getvalue()
    lines = [line for line in text.strip().splitlines() if line.startswith("{")]
    assert lines, f"no JSON line in captured output: {text!r}"
    return json.loads(lines[-1])  # type: ignore[no-any-return]


def test_emits_json_with_iso_timestamp(log_stream: io.StringIO) -> None:
    get_logger("test").info("hello", k="v")
    record = _parse(log_stream)
    assert record["event"] == "hello"
    assert record["k"] == "v"
    assert record["level"] == "info"
    assert record["logger"] == "test"
    # ISO-8601 UTC; timestamp must be present and look like a year-prefixed ISO date.
    assert str(record["timestamp"]).startswith("20")


def test_redacts_email(log_stream: io.StringIO) -> None:
    get_logger("test").info("user.signup", email="alice@example.com", name="Alice")
    record = _parse(log_stream)
    assert record["email"] == REDACTED
    assert record["name"] == "Alice"  # non-denied passes through


def test_redacts_password_in_kwargs(log_stream: io.StringIO) -> None:
    get_logger("test").info("auth.attempt", password="hunter2")
    record = _parse(log_stream)
    assert record["password"] == REDACTED


def test_no_trace_id_when_no_span(log_stream: io.StringIO) -> None:
    """Without an active OTel span, we don't fake a trace_id — the field is
    absent rather than "0000…". This keeps observability search filters honest."""
    get_logger("test").info("standalone")
    record = _parse(log_stream)
    assert "trace_id" not in record
    assert "span_id" not in record


def test_request_id_from_contextvars(log_stream: io.StringIO) -> None:
    """The middleware binds request_id into structlog.contextvars; downstream
    log lines must inherit it via merge_contextvars."""
    structlog.contextvars.bind_contextvars(request_id="abc123")
    get_logger("test").info("hit")
    record = _parse(log_stream)
    assert record["request_id"] == "abc123"


def test_configure_logging_replaces_handlers_not_appends() -> None:
    """Calling configure_logging twice must not duplicate handlers."""
    configure_logging("INFO")
    configure_logging("INFO")
    # Exactly one handler on the root logger — second configure replaces, not appends.
    assert len(logging.getLogger().handlers) == 1


def test_stdlib_logging_also_flows_through_json_pipe(log_stream: io.StringIO) -> None:
    """Libraries using stdlib logging (sqlalchemy/langchain/uvicorn) must land in
    the same JSON pipe — that's the whole point of the stdlib bridge."""
    logging.getLogger("third_party").info("some library log")
    text = log_stream.getvalue()
    # The structlog ProcessorFormatter rendered the stdlib record as JSON.
    assert "some library log" in text
    # And it's JSON, not the stdlib default format.
    assert text.strip().splitlines()[-1].startswith("{")
