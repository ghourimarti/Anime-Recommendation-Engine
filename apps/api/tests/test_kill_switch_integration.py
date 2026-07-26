"""Sanity check: the existing LLM_ENABLED kill switch (built in service.py) still serves a clean degraded 200 through the API after the
quota + cost layers were inserted around it.

The kill-switch unit test lives at packages/retrieval/tests/test_service_resilience.py
— this test exercises the SAME switch end-to-end through the FastAPI route.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from anime_api.auth import AuthedUser, get_current_user
from anime_api.dependencies import get_repository, get_service, verify_db_ready
from anime_api.main import create_app
from anime_api.quota import get_cost_meter, get_quota_counter
from anime_core.cost_meter import CostMeter
from anime_core.fallback import DEGRADED_NOTICE, popular_fallback
from anime_core.quotas import QuotaCounter
from anime_core.schemas import RecommendationResult
from httpx import ASGITransport, AsyncClient


class KillSwitchAwareService:
    """Mirrors the real RecommendationService's kill-switch behavior: when
    LLM_ENABLED=false, return popular_fallback as a degraded result."""

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        import os

        if os.environ.get("LLM_ENABLED", "true").strip().lower() == "false":
            return popular_fallback(DEGRADED_NOTICE)
        # Not under test here.
        raise NotImplementedError

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""


@pytest_asyncio.fixture
async def kill_switch_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_repo: Any,
    quota_counter: QuotaCounter,
    cost_meter: CostMeter,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("LLM_ENABLED", "false")
    application = create_app()
    application.dependency_overrides[get_service] = lambda: KillSwitchAwareService()
    application.dependency_overrides[get_repository] = lambda: fake_repo
    application.dependency_overrides[verify_db_ready] = lambda: None
    application.dependency_overrides[get_current_user] = lambda: AuthedUser(
        id="killswitch_user", email=None
    )
    application.dependency_overrides[get_quota_counter] = lambda: quota_counter
    application.dependency_overrides[get_cost_meter] = lambda: cost_meter
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_kill_switch_returns_degraded_200_not_5xx(
    kill_switch_client: AsyncClient,
) -> None:
    response = await kill_switch_client.post("/v1/recommend", json={"query": "anything"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is True
    assert body["notice"] == DEGRADED_NOTICE
    # Popular fallback contains real corpus entries (Cowboy Bebop is one).
    titles = [r["title"] for r in body["recommendations"]]
    assert "Cowboy Bebop" in titles


@pytest.mark.asyncio
async def test_kill_switch_still_counts_toward_quota(
    fake_repo: Any, kill_switch_client: AsyncClient
) -> None:
    """A degraded response still occupies a quota slot — we shouldn't reward
    users with 'free' requests during a cost incident."""
    await kill_switch_client.post("/v1/recommend", json={"query": "q"})
    # query_count_inc=1, even though no LLM call ran (cost stays 0).
    assert len(fake_repo.recorded_usage) == 1
    assert fake_repo.recorded_usage[0]["query_count_inc"] == 1
    assert fake_repo.recorded_usage[0]["cost_usd"] == 0
