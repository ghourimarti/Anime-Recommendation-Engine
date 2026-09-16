"""Breaker transitions must be recorded once per CHANGE (Track O.4).

The counter exists to answer "did this dependency break, and did it recover".
Recording on every call instead of every change would bury that under normal
traffic — a breaker that never trips would still produce thousands of samples.
"""

from __future__ import annotations

import pytest
from anime_core import resilience as resilience_mod
from anime_core.resilience import AsyncCircuitBreaker, CircuitBreakerError, CircuitState


@pytest.fixture
def transitions(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(resilience_mod, "record_circuit_transition", lambda **kw: calls.append(kw))
    return calls


async def _boom() -> None:
    raise RuntimeError("dependency down")


async def _ok() -> str:
    return "fine"


@pytest.mark.asyncio
async def test_healthy_calls_record_nothing(transitions: list[dict]) -> None:
    breaker = AsyncCircuitBreaker(name="pgvector", fail_max=2)
    for _ in range(5):
        assert await breaker.call(_ok) == "fine"
    assert transitions == []


@pytest.mark.asyncio
async def test_opening_is_recorded_once_not_per_failure(transitions: list[dict]) -> None:
    breaker = AsyncCircuitBreaker(name="pgvector", fail_max=2, reset_timeout=60.0)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(_boom)
    # Further calls fast-fail while open; they must not re-record the transition.
    for _ in range(3):
        with pytest.raises(CircuitBreakerError):
            await breaker.call(_boom)

    assert transitions == [{"breaker": "pgvector", "state": "open"}]


@pytest.mark.asyncio
async def test_recovery_path_records_half_open_then_closed(transitions: list[dict]) -> None:
    """open → half_open → closed is the sequence that proves a dependency came back."""
    breaker = AsyncCircuitBreaker(name="bm25_fts", fail_max=1, reset_timeout=0.0)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    assert breaker.state is CircuitState.HALF_OPEN  # reset_timeout elapsed
    assert await breaker.call(_ok) == "fine"

    assert [t["state"] for t in transitions] == ["open", "half_open", "closed"]
    assert {t["breaker"] for t in transitions} == {"bm25_fts"}
