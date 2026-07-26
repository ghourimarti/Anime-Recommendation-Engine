"""Unit tests for QuotaCounter.

Uses InMemoryCache (the test double) so these tests run without Redis. The
midnight rollover is tested by passing an injectable `now` — that's the whole
reason `incr_and_check` accepts `now`, so we never depend on freezegun.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from anime_core.cache import InMemoryCache, NullCache
from anime_core.quotas import QuotaCounter


@pytest.mark.asyncio
async def test_first_call_counts_one_and_reports_remaining() -> None:
    counter = QuotaCounter(InMemoryCache())
    result = await counter.incr_and_check(
        user_id="u1", limit=20, now=datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    )
    assert result.count == 1
    assert result.remaining == 19
    assert result.over_limit is False
    # ~12 hours until the next UTC midnight, give or take a second of rounding.
    assert 11 * 3600 < result.retry_after_seconds <= 12 * 3600


@pytest.mark.asyncio
async def test_under_limit_does_not_trip() -> None:
    counter = QuotaCounter(InMemoryCache())
    user, limit, now = "u2", 5, datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    for _ in range(limit):
        result = await counter.incr_and_check(user_id=user, limit=limit, now=now)
        assert result.over_limit is False
    assert result.remaining == 0  # exactly at the limit, last call


@pytest.mark.asyncio
async def test_over_limit_trips_on_next_call() -> None:
    counter = QuotaCounter(InMemoryCache())
    user, limit, now = "u3", 3, datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    for _ in range(limit):
        await counter.incr_and_check(user_id=user, limit=limit, now=now)
    result = await counter.incr_and_check(user_id=user, limit=limit, now=now)
    assert result.count == 4
    assert result.over_limit is True
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_per_user_isolation() -> None:
    counter = QuotaCounter(InMemoryCache())
    now = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    a = await counter.incr_and_check(user_id="alice", limit=2, now=now)
    b = await counter.incr_and_check(user_id="bob", limit=2, now=now)
    assert a.count == 1
    assert b.count == 1  # alice's increment must not leak into bob's bucket


@pytest.mark.asyncio
async def test_resets_at_midnight() -> None:
    counter = QuotaCounter(InMemoryCache())
    today = datetime(2026, 6, 6, 23, 59, tzinfo=UTC)
    tomorrow = datetime(2026, 6, 7, 0, 0, 1, tzinfo=UTC)
    user, limit = "u4", 1
    first = await counter.incr_and_check(user_id=user, limit=limit, now=today)
    assert first.count == 1
    over = await counter.incr_and_check(user_id=user, limit=limit, now=today)
    assert over.over_limit is True
    # Cross UTC midnight — new bucket key, count starts over.
    reset = await counter.incr_and_check(user_id=user, limit=limit, now=tomorrow)
    assert reset.count == 1
    assert reset.over_limit is False


@pytest.mark.asyncio
async def test_ttl_rounds_up_to_one_at_midnight_boundary() -> None:
    """A request milliseconds before midnight must NOT get TTL=0 (no-expiry in Redis)."""
    counter = QuotaCounter(InMemoryCache())
    just_before_midnight = datetime(2026, 6, 6, 23, 59, 59, 500_000, tzinfo=UTC)
    result = await counter.incr_and_check(user_id="u5", limit=20, now=just_before_midnight)
    assert result.retry_after_seconds >= 1


@pytest.mark.asyncio
async def test_null_cache_disables_the_gate() -> None:
    """With caching off (NullCache), the counter degrades to 0 — the app boots
    and serves traffic even without Redis. (graceful
    degradation: caching failures never break the request path.)"""
    counter = QuotaCounter(NullCache())
    result = await counter.incr_and_check(
        user_id="u6", limit=20, now=datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    )
    assert result.count == 0
    assert result.over_limit is False


@pytest.mark.asyncio
async def test_seconds_until_midnight_is_full_24h_just_after_midnight() -> None:
    counter = QuotaCounter(InMemoryCache())
    just_after_midnight = datetime(2026, 6, 6, 0, 0, 1, tzinfo=UTC)
    result = await counter.incr_and_check(user_id="u7", limit=20, now=just_after_midnight)
    # Should be ~24h - 1s = 86399s, give or take rounding.
    assert 86_390 <= result.retry_after_seconds <= 86_400
    assert result.retry_after_seconds == int(
        (
            (just_after_midnight + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            - just_after_midnight
        ).total_seconds()
    )
