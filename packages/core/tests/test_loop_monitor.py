"""I.F1b: the event-loop lag sampler.

Loop lag is the named cause behind the rerank wall-clock/compute gap. Without it
the gap has no owner, and every diagnosis lands on the cross-encoder.

Assertions are about BEHAVIOUR (does it sample, does it clamp, does it stop), not
about timing values — a test that asserts "lag < 5ms" fails on a loaded CI box and
teaches you to ignore it.
"""

from __future__ import annotations

import asyncio

import pytest
from anime_core.observability import loop_monitor as lm


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    seen: list[float] = []
    monkeypatch.setattr(lm, "record_loop_lag", seen.append)
    return seen


async def test_samples_are_recorded(recorded: list[float]) -> None:
    task = lm.start(0.01)
    await asyncio.sleep(0.12)
    await lm.stop(task)
    assert recorded, "the sampler produced no samples at all"


async def test_stop_cancels_cleanly(recorded: list[float]) -> None:
    task = lm.start(0.01)
    await asyncio.sleep(0.05)
    await lm.stop(task)
    assert task.done()
    # Must not leave the CancelledError to surface as an unretrieved exception.
    assert task.cancelled() or task.exception() is None


async def test_stop_tolerates_none() -> None:
    """Shutdown must not explode if startup never got far enough to start it."""
    await lm.stop(None)


async def test_never_records_negative(recorded: list[float]) -> None:
    """OTel histograms REJECT negative values — silently, one drop per record.

    This project has already shipped that bug once (the confidence histogram
    recorded raw logits, most of which are negative, and was quietly empty for the
    majority of queries). A monotonic clock plus the clamp is belt and braces.
    """
    task = lm.start(0.01)
    await asyncio.sleep(0.08)
    await lm.stop(task)
    assert all(v >= 0.0 for v in recorded), f"negative lag recorded: {recorded}"


async def test_detects_a_blocked_loop(recorded: list[float]) -> None:
    """The whole point: a blocking call must show up as lag.

    Mirrors the production effect measured 2026-09-20 — a CPU-bound section that
    never yields inflated the same to_thread+wait_for path from 0.050s to 0.354s.
    """
    task = lm.start(0.01)
    await asyncio.sleep(0.05)
    baseline = max(recorded, default=0.0)
    recorded.clear()

    # Block the loop outright: no await inside, so nothing else can run.
    deadline = asyncio.get_running_loop().time() + 0.25
    while asyncio.get_running_loop().time() < deadline:
        pass
    await asyncio.sleep(0.02)
    await lm.stop(task)

    assert recorded, "no sample taken across the blocking section"
    assert max(recorded) > baseline, (
        f"blocking the loop for 250ms produced max lag {max(recorded):.4f}s, "
        f"no worse than the idle baseline {baseline:.4f}s — the sampler is not "
        "measuring scheduling delay"
    )
