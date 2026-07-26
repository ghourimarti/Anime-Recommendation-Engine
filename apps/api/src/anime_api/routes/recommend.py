"""Recommendation endpoints.

POST /v1/recommend        -> structured, grounded Recommendations; persisted to
                             query_history (the canonical, storable result).
POST /v1/recommend/stream -> SSE token stream of prose (the live UX view; NOT
                             persisted — the structured call is the record).

This route adds: per-user quota gate (Redis), per-tenant cost recording
(Postgres usage_daily) on the structured path. Streaming cost recording is
deferred to the observability layer (Langfuse handles streaming usage natively).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

from anime_core.cost_meter import LAST_USAGE, CostMeter, UnknownModelError
from anime_core.observability.metrics import record_llm_call, record_unpriced_llm_call
from anime_core.streaming import sse_event
from anime_retrieval.cached_service import Recommender
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from anime_api.auth import AuthedUser, get_current_user
from anime_api.dependencies import get_repository, get_service
from anime_api.quota import enforce_quota, get_cost_meter
from anime_api.repository import Repository
from anime_api.schemas import RecommendationOut, RecommendRequest, RecommendResponse
from anime_api.timing import time_server_work

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    body: RecommendRequest,
    user: AuthedUser = Depends(get_current_user),
    _quota: None = Depends(enforce_quota),  # 429 + Retry-After if over daily limit
    repo: Repository = Depends(get_repository),
    service: Recommender = Depends(get_service),
    cost_meter: CostMeter = Depends(get_cost_meter),
) -> RecommendResponse:
    # No user_id passed to the service: recommendations are public + non-personalized
    # in v1, so the response/semantic cache stays GLOBAL (max hit rate). The user id
    # scopes only the per-user history record below.
    # time_server_work() sets the X-Server-Ms response header read by the k6 load
    # harness (load-test timing harness). Scope: just the recommend pipeline call —
    # NOT the DB writes below, because those are bookkeeping the client doesn't
    # wait on conceptually.
    with time_server_work():
        result = await service.recommend(body.query)
    items = [RecommendationOut.from_core(r) for r in result.items]
    await repo.ensure_user(user_id=user.id, email=user.email)
    query_history_id = await repo.add_query_history(
        user_id=user.id, query=body.query, response=result.model_dump()
    )

    # Cost meter: record this request in usage_daily. We ALWAYS record the
    # query (so the durable count matches the quota gate), but tokens/cost are
    # only non-zero when the LLM actually ran — kill switch / degraded paths
    # leave LAST_USAGE unset, which correctly records query_count=1, cost=0.
    usage = LAST_USAGE.get()
    input_tokens = output_tokens = 0
    cost = Decimal("0")
    if usage is not None:
        # Record the tokens FIRST, unconditionally. They are measured facts, and
        # they're what makes an unpriced call recoverable: with tokens on the row
        # you can backfill the cost once the rate is known. The old code assigned
        # them inside the try, so an unknown model threw them away too — losing
        # both the cost AND the only evidence needed to reconstruct it.
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        try:
            cost = cost_meter.cost_for(
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
            record_llm_call(
                model=usage.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=float(
                    cost
                ),  # OTel instruments take float; Decimal stays authoritative in the DB
            )
        except UnknownModelError:
            # Don't 500 the user over a billing config gap — but this is real
            # money going unattributed, so log at ERROR (not warning) and count
            # it, so the alert fires instead of the line scrolling past.
            logger.error(
                "no price for model=%s — recording %d in / %d out tokens at cost=0. "
                "Add it to LLM_PRICING; priced models: %s",
                usage.model,
                input_tokens,
                output_tokens,
                cost_meter.known_models,
            )
            record_unpriced_llm_call(model=usage.model)
    await repo.record_usage(
        user_id=user.id,
        day=datetime.now(UTC).date(),
        query_count_inc=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )

    return RecommendResponse(
        query=body.query,
        query_history_id=query_history_id,
        recommendations=items,
        # A refusal is still HTTP 200: the request was served correctly, the honest
        # answer just isn't a list of anime. It is NOT an error and NOT degraded.
        refusal=result.refusal,
        degraded=result.degraded,
        notice=result.notice,
    )


@router.post("/recommend/stream")
async def recommend_stream(
    body: RecommendRequest,
    request: Request,
    user: AuthedUser = Depends(get_current_user),
    _quota: None = Depends(enforce_quota),  # streaming counts toward quota too
    service: Recommender = Depends(get_service),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for token in service.astream(body.query):
            # Stop burning LLM tokens if the client navigated away.
            if await request.is_disconnected():
                break
            yield sse_event(token, event="token")
        yield sse_event("[DONE]", event="done")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
