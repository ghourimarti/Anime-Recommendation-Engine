"""QuotaCounter — Redis-backed per-user daily query gate.

Topology:
    Redis = request-gate     authoritative, atomic INCR+EXPIRE, sub-ms
    Postgres = durable record written via Repository.record_usage after success

The request-gate runs INLINE on every recommend call, so it MUST be cheap. We
use a single INCR+EXPIRE Redis op (pipelined). The Postgres write is the audit
trail and never gates the user response.

Key design notes (the senior tells):
  - **Calendar day, UTC.** Key includes YYYY-MM-DD; TTL is "seconds until next
    UTC midnight". Calendar-day windows are easier to communicate to users
    ("20 / day"), trivially expirable, and don't require holding 24h of state.
  - **No refund on failure.** INCR happens before the LLM call; an error after
    INCR keeps the count. Refund-on-failure is exploitable (spam failing
    requests, never count).
  - **Injectable clock.** `now` is a parameter, not `datetime.utcnow()` at the
    call site, so the midnight-rollover test doesn't need freezegun and the
    business logic stays pure.
  - **NullCache safe.** If Redis is unset (NullCache), every counter reads as 0
    and the gate is effectively disabled — the app boots without Redis and the
    quota is opt-in. Aligned with the rest of the cache stack's fail-open policy
    behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from anime_core.cache import Cache


@dataclass(frozen=True)
class CounterResult:
    """Result of a single quota check.

    `count` is the new value after increment. `remaining` is `limit - count`
    clamped to zero. `retry_after_seconds` is the seconds until the counter
    resets (UTC midnight) and is what we surface to the client via the
    Retry-After header on 429.
    """

    count: int
    remaining: int
    over_limit: bool
    retry_after_seconds: int


class QuotaCounter:
    """Per-user daily query counter, Redis-backed."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    @staticmethod
    def _key(user_id: str, now: datetime) -> str:
        return f"quota:{user_id}:{now.strftime('%Y-%m-%d')}"

    @staticmethod
    def _seconds_until_utc_midnight(now: datetime) -> int:
        # Round up: a request at 23:59:59.5 should get TTL=1, not 0 (Redis treats
        # 0 as "no expiry" — that would leak the counter into tomorrow).
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = next_midnight - now
        seconds = int(delta.total_seconds())
        return max(seconds, 1)

    async def incr_and_check(
        self,
        *,
        user_id: str,
        limit: int,
        now: datetime | None = None,
    ) -> CounterResult:
        """Atomically increment today's counter for `user_id`; report the result.

        Returns `over_limit=True` when the incremented count exceeds `limit`.
        Callers (e.g. the FastAPI `enforce_quota` dependency) decide what to do
        — raise 429, log, alert.
        """
        moment = now or datetime.now(UTC)
        ttl = self._seconds_until_utc_midnight(moment)
        count = await self._cache.incr_with_ttl(self._key(user_id, moment), ttl_seconds=ttl)
        return CounterResult(
            count=count,
            remaining=max(limit - count, 0),
            over_limit=count > limit,
            retry_after_seconds=ttl,
        )
