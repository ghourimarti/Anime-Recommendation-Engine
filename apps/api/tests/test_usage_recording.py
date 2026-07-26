"""Integration tests for the per-tenant cost meter.

We simulate the LLM by having the fake service set the LAST_USAGE ContextVar
before returning — which is exactly what BudgetedLLMClient → _LangChainClient
does in production. That keeps the test honest: it exercises the SAME
ContextVar path the route reads from.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from anime_core.cost_meter import LAST_USAGE, TokenUsage
from anime_core.schemas import RecommendationResult
from httpx import AsyncClient


class UsageEmittingService:
    """Fake service that emits LAST_USAGE before returning — mirrors what
    BudgetedLLMClient → _LangChainClient does in production."""

    def __init__(self, *, result: RecommendationResult, usage: TokenUsage | None) -> None:
        self._result = result
        self._usage = usage

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        if self._usage is not None:
            LAST_USAGE.set(self._usage)
        return self._result

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        if False:  # pragma: no cover — astream not used in these tests
            yield ""


@pytest.mark.asyncio
async def test_successful_recommend_records_usage_with_real_cost(
    fake_repo: Any, client: AsyncClient, app: Any
) -> None:
    """A successful LLM call → usage_daily row with the tokens AND computed cost."""
    from anime_api.dependencies import get_service

    usage = TokenUsage(model="llama-3.1-8b-instant", input_tokens=1_000, output_tokens=500)
    app.dependency_overrides[get_service] = lambda: UsageEmittingService(
        result=RecommendationResult(items=[]), usage=usage
    )

    response = await client.post("/v1/recommend", json={"query": "psychological"})
    assert response.status_code == 200

    assert len(fake_repo.recorded_usage) == 1
    row = fake_repo.recorded_usage[0]
    assert row["user_id"] == "user_test"
    assert row["day"] == datetime.now(UTC).date()
    assert row["query_count_inc"] == 1
    assert row["input_tokens"] == 1_000
    assert row["output_tokens"] == 500
    # cost_usd math verified in detail by test_cost_meter; here we just confirm
    # the route called cost_for with the right model + tokens.
    assert row["cost_usd"] == Decimal("0.00009")


@pytest.mark.asyncio
async def test_request_without_llm_usage_still_records_zero_cost(
    fake_repo: Any, client: AsyncClient, app: Any
) -> None:
    """Kill-switch / degraded paths don't emit LAST_USAGE — we MUST still record
    the query (so durable counts match quota) at cost=0."""
    from anime_api.dependencies import get_service

    app.dependency_overrides[get_service] = lambda: UsageEmittingService(
        result=RecommendationResult(items=[], degraded=True, notice="degraded"),
        usage=None,  # explicitly: no LLM call happened
    )

    response = await client.post("/v1/recommend", json={"query": "anything"})
    assert response.status_code == 200

    assert len(fake_repo.recorded_usage) == 1
    row = fake_repo.recorded_usage[0]
    assert row["query_count_inc"] == 1
    assert row["input_tokens"] == 0
    assert row["output_tokens"] == 0
    assert row["cost_usd"] == Decimal("0")


@pytest.mark.asyncio
async def test_unknown_model_logs_but_does_not_500(
    fake_repo: Any, client: AsyncClient, app: Any
) -> None:
    """An unknown model must not 500 the user — but it must not lose the tokens either.

    The route logs at ERROR and records cost=0 (the operator adds the model to
    LLM_PRICING), while the user still gets their recommendation.

    Crucially the TOKEN COUNTS are still written. They are measured facts, and
    they are the only evidence that makes an unpriced call recoverable: with them
    on the row you can backfill the true cost once the rate is known. The earlier
    version of this route assigned tokens inside the try block, so an unknown
    model discarded them along with the cost — destroying both the number and any
    means of reconstructing it.
    """
    from anime_api.dependencies import get_service

    usage = TokenUsage(model="future-model-not-priced", input_tokens=10, output_tokens=5)
    app.dependency_overrides[get_service] = lambda: UsageEmittingService(
        result=RecommendationResult(items=[]), usage=usage
    )

    response = await client.post("/v1/recommend", json={"query": "test"})
    assert response.status_code == 200
    row = fake_repo.recorded_usage[0]
    assert row["cost_usd"] == Decimal("0")  # can't price it
    assert row["input_tokens"] == 10  # ...but never lose the evidence
    assert row["output_tokens"] == 5
