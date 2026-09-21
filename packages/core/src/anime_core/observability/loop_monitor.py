"""Event-loop lag sampler.

WHAT IT MEASURES. Sleep for a fixed interval, then ask how much LATER than
requested the wakeup actually happened. `asyncio.sleep(0.25)` guarantees *at
least* 250ms; anything beyond that is time the loop could not get back to this
coroutine, i.e. scheduling delay. That excess is the metric.

WHY IT EXISTS. `anime.retrieval.stage.duration{stage="rerank"}` is wall-clock
across an `await`, so it silently includes this delay and attributes it to the
cross-encoder. Measured 2026-09-20 inside the API container:

    .predict() on 20 real-length pairs, warm       0.056 s
    same via to_thread+wait_for, IDLE loop         0.050 s
    same via to_thread+wait_for, BUSY loop         0.257-0.354 s
    what the stage metric reports in production    1.250 s p50

Compute is ~4% of the reported number. Without this sampler the other 96% has no
name, so every diagnosis lands on the reranker -- which is how a model swap that
the golden set had already measured as a -0.045 success@1 regression kept looking
like the obvious fix.

The failure mode it makes visible is not a latency nuisance. Loop lag inflates
rerank wall-clock past RERANK_TIMEOUT; the timeout yields no confidence score;
should_use_venue(None) fails safe to hosted. So a saturated event loop silently
makes the self-hosted GPU unreachable, while every engine panel stays green.

OBSERVER EFFECT. The sampler is itself work on the loop it measures. 250ms is
chosen against the effect size actually measured (250-350ms stalls), not picked
round: fast enough to catch them, ~4 wakeups/sec of self-inflicted load.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from anime_core.observability.metrics import record_loop_lag

# Matched to the measured stall size (250-350ms), not chosen for neatness. A 1s
# interval aliases past exactly the stalls this exists to catch; 100ms triples the
# self-inflicted load for no extra signal.
DEFAULT_INTERVAL_S = 0.25


async def _sample_forever(interval: float) -> None:
    while True:
        started = time.monotonic()
        await asyncio.sleep(interval)
        # monotonic, never time.time(): a wall-clock step (NTP, VM resume) would
        # produce a NEGATIVE lag, and OTel histograms REJECT negative values --
        # silently, one dropped record per occurrence. This project has already
        # shipped that exact bug once, on the confidence histogram.
        lag = (time.monotonic() - started) - interval
        record_loop_lag(max(0.0, lag))


def start(interval: float = DEFAULT_INTERVAL_S) -> asyncio.Task[None]:
    """Start sampling. The caller MUST keep the returned reference.

    A bare `asyncio.create_task(...)` with nothing holding it can be garbage
    collected mid-flight, and the metric then stops with no error anywhere -- an
    instrument that looks wired up and is quietly dead, which is the failure class
    this whole track exists to catch.
    """
    return asyncio.create_task(_sample_forever(interval), name="loop-lag-monitor")


async def stop(task: asyncio.Task[None] | None) -> None:
    """Cancel the sampler and wait for it to unwind. Safe to call with None."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
