"""Tests for ServerTimingMiddleware + time_server_work() — the load-test timing harness.

Verifies:
  - Routes that call time_server_work() emit an X-Server-Ms response header
  - Routes that don't call it emit NO header (consumers must check presence)
  - The header is a positive float (ms)
  - Streaming responses don't receive the header (timer hasn't finished when
    http.response.start is sent — k6 measures TTFT client-side instead)
  - ContextVar is reset per request — no cross-request leakage
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from anime_api.middleware import ServerTimingMiddleware
from anime_api.timing import server_duration_ms, time_server_work
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with just ServerTimingMiddleware mounted.

    No DB, no Clerk, no LangChain — the middleware is its own concern.
    """
    app = FastAPI()
    app.add_middleware(ServerTimingMiddleware)

    @app.get("/timed")
    async def timed() -> dict[str, str]:
        with time_server_work():
            await asyncio.sleep(0.005)  # 5ms of "work"
        return {"ok": "true"}

    @app.get("/untimed")
    async def untimed() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/timed-stream")
    async def timed_stream() -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            with time_server_work():
                for i in range(3):
                    await asyncio.sleep(0.001)
                    yield f"chunk-{i}\n"

        return StreamingResponse(gen(), media_type="text/plain")

    return app


@pytest.mark.asyncio
async def test_timed_route_emits_header() -> None:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/timed")
    assert response.status_code == 200
    assert "x-server-ms" in response.headers
    ms = float(response.headers["x-server-ms"])
    # Lower-bound (sleep should be >= 5ms): generous floor for slow CI runners.
    assert ms >= 3.0, f"expected ≥3ms, got {ms}"
    # Upper-bound sanity: 1s is wildly more than 5ms even on a frozen CI.
    assert ms < 1000.0, f"timing wildly off: {ms}ms for a 5ms sleep"


@pytest.mark.asyncio
async def test_untimed_route_has_no_header() -> None:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/untimed")
    assert response.status_code == 200
    assert "x-server-ms" not in response.headers


@pytest.mark.asyncio
async def test_streaming_route_has_no_header() -> None:
    """SSE responses can't emit the header — http.response.start fires before
    the timer ends. xk6-sse measures TTFT client-side instead."""
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/timed-stream")
    assert response.status_code == 200
    # http.response.start is sent before the with block exits → header absent.
    assert "x-server-ms" not in response.headers
    # But the body still streamed correctly.
    assert "chunk-0" in response.text


@pytest.mark.asyncio
async def test_contextvar_reset_across_requests() -> None:
    """A previous request's timing must not leak into a subsequent untimed one."""
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/timed")
        r2 = await client.get("/untimed")
    assert "x-server-ms" in r1.headers
    assert "x-server-ms" not in r2.headers


def test_contextvar_default_is_none() -> None:
    """Sanity: the ContextVar starts as None outside any time_server_work() block."""
    assert server_duration_ms.get() is None


def test_time_server_work_sets_positive_float() -> None:
    """Synchronous unit test of the context manager itself."""
    with time_server_work():
        # Burn a tiny amount of wall clock so the timer reads non-zero.
        for _ in range(1000):
            pass
    value = server_duration_ms.get()
    assert value is not None
    assert value >= 0.0
