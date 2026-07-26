"""End-to-end observability checks.

Asserts the wire-level behavior:
  - Every request emits structured JSON log lines through the configured stream.
  - The middleware binds request_id to structlog contextvars (visible in lines).
  - PII fields (email, query) are masked to [REDACTED] before serialization.
  - Each response carries an X-Request-Id header (the support flow's entry point).

We can't easily assert on real OTel exports under ASGITransport without spinning
up a collector — those are verified at the unit level in
packages/core/tests/test_otel.py.
"""

from __future__ import annotations

import io
import json

import pytest
import structlog
from anime_core.observability.logging import configure_logging
from anime_core.observability.redaction import REDACTED


@pytest.fixture
def log_stream(app) -> io.StringIO:  # type: ignore[no-untyped-def]
    """Reconfigure logging into a buffer AFTER `app` runs (whose `create_app()`
    calls `configure_logging()` again — order matters, ours has to win)."""
    buf = io.StringIO()
    configure_logging("INFO", stream=buf)
    structlog.contextvars.clear_contextvars()
    return buf


def _json_lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in buf.getvalue().strip().splitlines() if line.startswith("{")
    ]


@pytest.mark.asyncio
async def test_request_emits_json_log_with_request_id(
    log_stream: io.StringIO,
    client,  # type: ignore[no-untyped-def]
) -> None:
    """Hitting /health is enough — the middleware fires on every route."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    # The middleware echoes X-Request-Id back.
    assert "x-request-id" in {k.lower() for k in resp.headers}

    records = _json_lines(log_stream)
    # We expect at least the request.start + request.end events.
    starts = [r for r in records if r.get("event") == "request.start"]
    ends = [r for r in records if r.get("event") == "request.end"]
    assert starts, f"no request.start log; saw: {records}"
    assert ends
    # request_id is bound by the middleware before request.start fires.
    assert starts[0]["request_id"] == resp.headers["x-request-id"]


@pytest.mark.asyncio
async def test_email_in_log_kwargs_is_redacted(
    log_stream: io.StringIO,
    client,  # type: ignore[no-untyped-def]
) -> None:
    """A deliberate log call with a sensitive value must come out masked."""
    structlog.get_logger("test").info("user.signup", email="alice@example.com")
    records = _json_lines(log_stream)
    matching = [r for r in records if r.get("event") == "user.signup"]
    assert matching
    assert matching[0]["email"] == REDACTED


@pytest.mark.asyncio
async def test_request_log_does_not_leak_query_string(
    log_stream: io.StringIO,
    client,  # type: ignore[no-untyped-def]
) -> None:
    """The middleware logs path + method but the structlog redaction catches
    any caller that accidentally logs a `query` kwarg downstream."""
    # Simulate a downstream log call that includes the query content.
    structlog.get_logger("anime_api.test").info(
        "downstream.processing", query="a sensitive user query"
    )
    records = _json_lines(log_stream)
    matching = [r for r in records if r.get("event") == "downstream.processing"]
    assert matching
    assert matching[0]["query"] == REDACTED
