"""Test fixtures — app with overridden dependencies (no DB, no API key).

Lifespan does NOT run under httpx ASGITransport, so the heavy singletons
(embedder/reranker/llm/quota_counter/cost_meter) are never constructed; we
override every dependency that would touch them.
"""

from __future__ import annotations

import os

# Disable the OTel SDK in tests BEFORE importing the API package — otherwise the
# BatchSpanProcessor's worker thread tries to flush to a non-existent
# localhost:4317 collector and floods stderr with grpc connection errors.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from anime_api.auth import AuthedUser, get_current_user
from anime_api.dependencies import get_repository, get_service, verify_db_ready
from anime_api.main import create_app
from anime_api.quota import get_cost_meter, get_quota_counter
from anime_core.cache import InMemoryCache
from anime_core.cost_meter import CostMeter
from anime_core.quotas import QuotaCounter
from anime_core.schemas import Recommendation, RecommendationResult
from httpx import ASGITransport, AsyncClient


class FakeService:
    def __init__(self, result: RecommendationResult) -> None:
        self._result = result

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        return self._result

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        for token in ["Here ", "are ", "some ", "anime"]:
            yield token


class FakeRepository:
    def __init__(self) -> None:
        self.added_history: list[dict[str, Any]] = []
        self.added_feedback: list[dict[str, Any]] = []
        self.ensured_users: list[str] = []
        self.recorded_usage: list[dict[str, Any]] = []

    async def ensure_user(self, *, user_id: str, email: str | None) -> None:
        self.ensured_users.append(user_id)

    async def add_query_history(
        self, *, user_id: str | None, query: str, response: dict[str, Any]
    ) -> int:
        self.added_history.append({"user_id": user_id, "query": query, "response": response})
        return 1

    async def list_query_history(
        self, *, user_id: str | None, limit: int, offset: int
    ) -> list[Any]:
        return [
            SimpleNamespace(
                id=1,
                query="psychological thriller",
                response={
                    "items": [{"mal_id": 19, "title": "Monster", "summary": "s", "why_match": "w"}]
                },
                created_at=datetime.now(UTC),
            )
        ]

    async def add_feedback(
        self, *, user_id: str | None, query_history_id: int | None, mal_id: int, rating: int
    ) -> int:
        self.added_feedback.append({"mal_id": mal_id, "rating": rating})
        return 7

    async def record_usage(
        self,
        *,
        user_id: str,
        day: date,
        query_count_inc: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        self.recorded_usage.append(
            {
                "user_id": user_id,
                "day": day,
                "query_count_inc": query_count_inc,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            }
        )


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def quota_counter() -> QuotaCounter:
    """Fresh QuotaCounter per test — InMemoryCache means no Redis required."""
    return QuotaCounter(InMemoryCache())


# Pricing is INJECTED here, never read from the ambient LLM_PRICING env var.
#
# Two reasons, and the first one cost a green CI run: CostMeter() with no table
# reads LLM_PRICING and raises PricingConfigError when it is unset, so on a
# machine without a .env — every CI runner — all 27 tests that build the `app`
# fixture error out before their first assertion. Second, a test that reads live
# rates starts failing the day a provider changes one, which is noise, not signal
# (packages/core/tests/test_cost_meter.py makes the same argument).
#
# "future-model-not-priced" is deliberately absent: test_usage_recording asserts
# that an unknown model records tokens at cost 0 instead of 500ing.
TEST_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "llama-3.1-8b-instant": (Decimal("0.05"), Decimal("0.08")),
    "openai/gpt-oss-20b": (Decimal("0.075"), Decimal("0.30")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}


@pytest.fixture
def cost_meter() -> CostMeter:
    return CostMeter(pricing=TEST_PRICING)


@pytest.fixture
def app(  # type: ignore[no-untyped-def]
    fake_repo: FakeRepository,
    quota_counter: QuotaCounter,
    cost_meter: CostMeter,
):
    application = create_app()
    result = RecommendationResult(
        items=[Recommendation(mal_id=19, title="Monster", summary="s", why_match="w")]
    )
    application.dependency_overrides[get_service] = lambda: FakeService(result)
    application.dependency_overrides[get_repository] = lambda: fake_repo
    application.dependency_overrides[verify_db_ready] = lambda: None
    application.dependency_overrides[get_current_user] = lambda: AuthedUser(
        id="user_test", email="test@example.com"
    )
    application.dependency_overrides[get_quota_counter] = lambda: quota_counter
    application.dependency_overrides[get_cost_meter] = lambda: cost_meter
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
