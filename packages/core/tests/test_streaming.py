"""Tests for the streaming helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.streaming import accumulate, sse_event


def test_sse_event_basic() -> None:
    assert sse_event("hello") == "data: hello\n\n"


def test_sse_event_with_name() -> None:
    assert sse_event("hi", event="token") == "event: token\ndata: hi\n\n"


def test_sse_event_multiline() -> None:
    # newlines split into multiple data: lines per the SSE spec
    assert sse_event("a\nb") == "data: a\ndata: b\n\n"


@pytest.mark.asyncio
async def test_accumulate_tees_stream() -> None:
    async def gen() -> AsyncIterator[str]:
        for t in ["x", "y", "z"]:
            yield t

    sink: list[str] = []
    out = [t async for t in accumulate(gen(), sink)]
    assert out == ["x", "y", "z"]
    assert "".join(sink) == "xyz"
