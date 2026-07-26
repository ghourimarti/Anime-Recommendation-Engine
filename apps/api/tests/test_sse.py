"""POST /v1/recommend/stream — SSE framing test."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stream_emits_sse_frames(client: AsyncClient) -> None:
    resp = await client.post("/v1/recommend/stream", json={"query": "fun comedy"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    # token events for each streamed chunk, then a terminal done event
    assert "event: token" in body
    assert "data: Here " in body
    assert "event: done" in body
    assert "[DONE]" in body
