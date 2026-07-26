"""Handler contract + the shared dependency bundle handlers receive.

Handlers are async callables that take the job payload + a `HandlerContext`
(cache + a DB session factory). They assume they MAY run more than once
(at-least-once delivery) — dedup is the consumer's job, not theirs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from anime_core.cache import Cache

# A handler: (payload, ctx) -> awaitable. Raising propagates to the consumer,
# which does NOT delete the message → SQS redelivers → DLQ after maxReceiveCount.
Handler = Callable[[dict[str, Any], "HandlerContext"], Awaitable[None]]


@dataclass
class HandlerContext:
    """What every handler needs. `session_factory` is an async context manager
    factory (anime_core.db.engine.session_scope) so handlers that touch the DB
    open a scoped session; cache-only handlers ignore it."""

    cache: Cache
    session_factory: Any  # Callable[[], AbstractAsyncContextManager[AsyncSession]]
