"""Server-side stage timing — ContextVar + context manager.

Purpose (load-test timing harness):
Surface server-processing latency to clients via an `X-Server-Ms` response
header so the k6 load harness can validate the latency NFRs without correlating
HTTP duration with Langfuse traces post-hoc.

Naming honesty: the wrapped span is the *recommend pipeline* (cache lookup +
hybrid retrieval + rerank + MMR + LLM generation), NOT just retrieval. The
header is named `X-Server-Ms` to reflect what it actually measures. For
retrieval-stage-isolated timing, see Langfuse traces.

Why a ContextVar (not a request-scoped attribute):
  - The `ServerTimingMiddleware` is pure-ASGI (must not buffer streaming
    responses), so it has no access to a FastAPI `Request` object to attach
    state to. A ContextVar is the canonical asyncio-safe alternative.
  - Each request gets a fresh value because the middleware resets it at
    request start; pure-ASGI ContextVar semantics make this safe across
    concurrent requests.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# None = not set during this request → middleware emits no header.
server_duration_ms: ContextVar[float | None] = ContextVar(
    "anime_api_server_duration_ms", default=None
)


@contextmanager
def time_server_work() -> Iterator[None]:
    """Time a server-side work block and stash the result in the ContextVar.

    The middleware reads this value AFTER the route handler returns and
    emits it as `X-Server-Ms`. Wrap the heaviest server-side call (e.g.
    `service.recommend()`) — that's the number that maps to "server-side
    p95" in the k6 reports.

    Usage:
        with time_server_work():
            result = await service.recommend(query)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        server_duration_ms.set((time.perf_counter() - start) * 1000.0)
