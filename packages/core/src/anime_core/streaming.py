"""Streaming helpers shared between the LLM layer and the API.

Kept tiny and transport-agnostic: `sse_event` formats a Server-Sent Event frame;
`accumulate` tees a token stream so the API can stream to the client AND keep the
full text (e.g. to persist to query_history) without consuming the stream twice.
"""

from __future__ import annotations

from collections.abc import AsyncIterator


def sse_event(data: str, *, event: str | None = None) -> str:
    """Format a single Server-Sent Event frame.

    Newlines in `data` are split across multiple `data:` lines per the SSE spec.
    """
    lines = []
    if event is not None:
        lines.append(f"event: {event}")
    for chunk in data.split("\n"):
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


async def accumulate(
    tokens: AsyncIterator[str],
    sink: list[str],
) -> AsyncIterator[str]:
    """Yield each token through while appending it to `sink`.

    Lets a caller stream tokens to the client and recover the full text after the
    stream completes (sink == "".join(sink)).
    """
    async for token in tokens:
        sink.append(token)
        yield token
