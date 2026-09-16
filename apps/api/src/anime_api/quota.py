"""Quota enforcement at the HTTP boundary.

`enforce_quota` is the FastAPI dependency that gates every LLM-bearing route.
It's a thin shim: get the per-process QuotaCounter off `app.state`, INCR the
user's daily key in Redis, and raise 429 with `Retry-After` if over.

The QuotaCounter + CostMeter singletons live on `app.state` (built in
`lifespan.py`), not constructed per-request — building them per-request would
add a Redis connection + a dict allocation to every call (the cost-control
layer should not BE a cost).

`get_quota_counter` and `get_cost_meter` exist as named dependencies so tests
can override them via `app.dependency_overrides` — the standard FastAPI test
pattern that the rest of the API already uses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from anime_core.cost_meter import CostMeter
from anime_core.jobs import JobPublisher
from anime_core.observability.metrics import record_quota_rejection
from anime_core.quotas import QuotaCounter
from fastapi import Depends, HTTPException, Request, status

from anime_api.auth import AuthedUser, get_current_user
from anime_api.config import Settings, get_settings


def get_quota_counter(request: Request) -> QuotaCounter:
    """Per-request handle on the app-level QuotaCounter built in lifespan.py."""
    counter: QuotaCounter | None = getattr(request.app.state, "quota_counter", None)
    if counter is None:
        # Lifespan didn't run (test transport, or a misconfiguration). Fail closed
        # in production-ish env; tests override this dependency directly.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="quota counter not initialized",
        )
    return counter


def get_cost_meter(request: Request) -> CostMeter:
    """Per-request handle on the app-level CostMeter."""
    meter: CostMeter | None = getattr(request.app.state, "cost_meter", None)
    if meter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cost meter not initialized",
        )
    return meter


def get_job_publisher(request: Request) -> JobPublisher | None:
    """Per-request handle on the app-level SQS job publisher.

    Returns None if unset (e.g. tests that don't wire it) — callers treat a
    missing publisher as "async disabled" and degrade gracefully.
    """
    return getattr(request.app.state, "job_publisher", None)


async def enforce_quota(
    user: AuthedUser = Depends(get_current_user),
    counter: QuotaCounter = Depends(get_quota_counter),
    settings: Settings = Depends(get_settings),
) -> None:
    """Atomically increment today's quota for `user`; raise 429 if over the cap.

    Refunds are deliberately NOT issued on downstream failures — see quotas.py.
    The INCR happens here, before the LLM is touched; spending failures already
    counted is what prevents the "fail-spam to bypass quota" attack.
    """
    result = await counter.incr_and_check(
        user_id=user.id,
        limit=settings.quota_free_tier_daily,
        now=datetime.now(UTC),
    )
    if result.over_limit:
        record_quota_rejection(scope="user_daily")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"daily quota of {settings.quota_free_tier_daily} requests exceeded; "
                f"resets in {result.retry_after_seconds}s"
            ),
            headers={"Retry-After": str(result.retry_after_seconds)},
        )
