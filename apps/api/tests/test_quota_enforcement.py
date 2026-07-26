"""Integration tests for quota enforcement.

We tighten the daily quota to 3 via a `get_settings` override so the over-limit
case fires on the 4th request — no need to hammer the suite with 21 calls.
Re-uses the conftest `app` + `client` fixtures (which already wire FakeService +
FakeRepository + the new QuotaCounter/CostMeter overrides) so this test file
adds only the deltas.
"""

from __future__ import annotations

from typing import Any

import pytest
from anime_api.auth import AuthedUser, get_current_user
from anime_api.config import Settings, get_settings
from httpx import ASGITransport, AsyncClient


def _small_quota_settings() -> Settings:
    """Settings override — daily limit of 3 so we can prove 429 without 21 calls."""
    return Settings(quota_free_tier_daily=3, clerk_jwks_url="")


@pytest.fixture
def app_with_small_quota(app):  # type: ignore[no-untyped-def]
    """Same as the conftest app, but tightened to 3 queries/day."""
    app.dependency_overrides[get_settings] = _small_quota_settings
    return app


@pytest.fixture
async def small_quota_client(app_with_small_quota):  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app_with_small_quota)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_under_limit_returns_200(small_quota_client: AsyncClient) -> None:
    for _ in range(3):
        r = await small_quota_client.post("/v1/recommend", json={"query": "psychological"})
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_over_limit_returns_429_with_retry_after(
    small_quota_client: AsyncClient,
) -> None:
    # Exhaust the 3-per-day quota first.
    for _ in range(3):
        ok = await small_quota_client.post("/v1/recommend", json={"query": "psychological"})
        assert ok.status_code == 200, ok.text
    # 4th request → 429.
    refused = await small_quota_client.post("/v1/recommend", json={"query": "psychological"})
    assert refused.status_code == 429
    # Retry-After is the seconds until UTC midnight — must be present and positive.
    assert "retry-after" in {k.lower() for k in refused.headers}
    retry_after = int(refused.headers["retry-after"])
    assert 0 < retry_after <= 86400
    # The user-facing message names the limit so the frontend can show "20/day".
    assert "quota" in refused.json()["detail"].lower()


@pytest.mark.asyncio
async def test_streaming_endpoint_also_quota_gated(
    small_quota_client: AsyncClient,
) -> None:
    """The SSE route MUST count toward quota too — otherwise users could stream
    around the limit forever."""
    for _ in range(3):
        await small_quota_client.post("/v1/recommend/stream", json={"query": "p"})
    refused = await small_quota_client.post("/v1/recommend/stream", json={"query": "p"})
    assert refused.status_code == 429


@pytest.mark.asyncio
async def test_per_user_isolation(app_with_small_quota: Any) -> None:
    """User A exhausting their quota must NOT affect user B."""
    # First, user A burns the quota.
    app_with_small_quota.dependency_overrides[get_current_user] = lambda: AuthedUser(
        id="user_a", email="a@example.com"
    )
    transport = ASGITransport(app=app_with_small_quota)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(3):
            assert (await ac.post("/v1/recommend", json={"query": "q"})).status_code == 200
        assert (await ac.post("/v1/recommend", json={"query": "q"})).status_code == 429

    # Swap to user B — fresh bucket, fresh budget. (The QuotaCounter override
    # from conftest is shared across users, so isolation is by Redis key — which
    # in InMemoryCache is the user_id-scoped string.)
    app_with_small_quota.dependency_overrides[get_current_user] = lambda: AuthedUser(
        id="user_b", email="b@example.com"
    )
    transport = ASGITransport(app=app_with_small_quota)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        assert (await ac.post("/v1/recommend", json={"query": "q"})).status_code == 200
