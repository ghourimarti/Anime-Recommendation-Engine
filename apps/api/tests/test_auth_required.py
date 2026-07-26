"""Protected endpoints reject unauthenticated requests; writes are scoped to the user."""

from __future__ import annotations

import pytest
from anime_api.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_recommend_requires_auth() -> None:
    # App WITHOUT the get_current_user override → real auth gate runs.
    # No token + unconfigured Clerk → fail closed (not a 200).
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/recommend", json={"query": "thriller"})
    assert resp.status_code in (401, 503)  # never 200 without a valid token


@pytest.mark.asyncio
async def test_history_requires_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/history")
    assert resp.status_code in (401, 503)


@pytest.mark.asyncio
async def test_health_stays_open() -> None:
    # Health/readiness must NOT require auth (k8s probes hit them unauthenticated).
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_recommend_scopes_history_to_user(client: AsyncClient, fake_repo) -> None:  # type: ignore[no-untyped-def]
    # With the conftest override (user_test), the write is scoped to that user.
    resp = await client.post("/v1/recommend", json={"query": "thriller"})
    assert resp.status_code == 200
    assert fake_repo.ensured_users == ["user_test"]
    assert fake_repo.added_history[0]["user_id"] == "user_test"
