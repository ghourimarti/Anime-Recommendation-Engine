"""Resilience primitives: circuit breaker, timeout, retry, errors.

The typed errors are the contract the fallback logic is organized around — each
handler is "catch THIS, do THAT":
  - LLMUnavailableError / RetrievalUnavailableError: a whole capability is down →
    the service degrades to the popular fallback.
  - LLMDisabledError: the cost kill switch is engaged.
  - CircuitBreakerError: a breaker is open → fast-fail without touching the dep.

The circuit breaker is hand-rolled (async-native) rather than `pybreaker` (sync-
first). Same state machine — closed → open (after fail_max) → half-open (after
reset_timeout) → closed on a successful trial — but it composes cleanly with
asyncio and is fully unit-testable offline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


class CircuitBreakerError(RuntimeError):
    """Raised when a call is attempted while the breaker is open."""


class LLMUnavailableError(RuntimeError):
    """Every LLM tier failed; the service should degrade."""


class RetrievalUnavailableError(RuntimeError):
    """Every retrieval path failed; the service should degrade."""


class LLMDisabledError(RuntimeError):
    """The LLM kill switch is engaged (LLM_ENABLED=false)."""


class BudgetExceededError(RuntimeError):
    """Per-request token-budget guard refused an oversized input."""


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AsyncCircuitBreaker:
    """Minimal async circuit breaker.

    closed   → calls flow; failures counted.
    open      → calls fast-fail with CircuitBreakerError until reset_timeout elapses.
    half_open → one trial call allowed; success closes, failure re-opens.
    """

    def __init__(self, *, name: str, fail_max: int = 5, reset_timeout: float = 30.0) -> None:
        self.name = name
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and (time.monotonic() - self._opened_at) >= self._reset_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    async def call[T](self, func: Callable[[], Awaitable[T]]) -> T:
        if self.state is CircuitState.OPEN:
            raise CircuitBreakerError(f"{self.name} circuit is open")
        try:
            result = await func()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _on_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._fail_max:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("circuit %s opened after %d failures", self.name, self._failures)


async def with_timeout[T](func: Callable[[], Awaitable[T]], *, seconds: float) -> T:
    """Run `func`, cancelling it and raising TimeoutError if it exceeds `seconds`."""
    async with asyncio.timeout(seconds):
        return await func()


async def with_retry[T](
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry `func` with exponential backoff + jitter."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=0.5, max=4.0),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    ):
        with attempt:
            return await func()
    raise RuntimeError("unreachable")  # pragma: no cover


async def guarded[T](
    func: Callable[[], Awaitable[T]],
    *,
    breaker: AsyncCircuitBreaker,
    timeout_seconds: float,
) -> T:
    """Breaker (outermost, fast-fails when open) around a timeout-bounded call."""
    return await breaker.call(lambda: with_timeout(func, seconds=timeout_seconds))
