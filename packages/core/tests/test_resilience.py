"""Tests for the resilience primitives (breaker / timeout / retry)."""

from __future__ import annotations

import asyncio

import pytest
from anime_core.resilience import (
    AsyncCircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    guarded,
    with_retry,
    with_timeout,
)


async def _boom() -> None:
    raise RuntimeError("boom")


async def _ok() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_breaker_opens_after_fail_max() -> None:
    cb = AsyncCircuitBreaker(name="t", fail_max=3, reset_timeout=60.0)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    assert cb.state is CircuitState.OPEN
    # open → fast-fail without calling through
    with pytest.raises(CircuitBreakerError):
        await cb.call(_ok)


@pytest.mark.asyncio
async def test_breaker_half_opens_then_closes_on_success() -> None:
    cb = AsyncCircuitBreaker(name="t", fail_max=1, reset_timeout=0.0)  # immediate half-open
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state is CircuitState.HALF_OPEN  # reset_timeout=0 → immediately half-open
    result = await cb.call(_ok)  # trial succeeds
    assert result == "ok"
    assert cb.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_reopens_on_half_open_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import anime_core.resilience as res

    clock = {"t": 0.0}
    monkeypatch.setattr(res.time, "monotonic", lambda: clock["t"])

    cb = AsyncCircuitBreaker(name="t", fail_max=1, reset_timeout=10.0)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state is CircuitState.OPEN  # t=0, within reset window

    clock["t"] = 10.0
    assert cb.state is CircuitState.HALF_OPEN  # reset elapsed → trial allowed
    with pytest.raises(RuntimeError):
        await cb.call(_boom)  # trial fails → re-open at t=10

    clock["t"] = 11.0
    assert cb.state is CircuitState.OPEN  # 11 < 10+10 → still open


@pytest.mark.asyncio
async def test_with_timeout_raises_and_cancels() -> None:
    async def _slow() -> str:
        await asyncio.sleep(1.0)
        return "never"

    with pytest.raises(TimeoutError):
        await with_timeout(_slow, seconds=0.05)


@pytest.mark.asyncio
async def test_with_retry_succeeds_after_failures() -> None:
    calls = {"n": 0}

    async def _flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    result = await with_retry(_flaky, attempts=3)
    assert result == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_guarded_open_breaker_fast_fails() -> None:
    cb = AsyncCircuitBreaker(name="t", fail_max=1, reset_timeout=60.0)
    with pytest.raises(RuntimeError):
        await guarded(_boom, breaker=cb, timeout_seconds=1.0)
    # now open → guarded raises CircuitBreakerError without calling through
    with pytest.raises(CircuitBreakerError):
        await guarded(_ok, breaker=cb, timeout_seconds=1.0)
