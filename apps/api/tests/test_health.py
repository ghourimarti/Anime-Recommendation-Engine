"""Health/readiness + request-id middleware tests."""

from __future__ import annotations

import pytest
from anime_api.dependencies import verify_db_ready
from anime_api.main import create_app
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_has_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert "x-request-id" in {k.lower() for k in resp.headers}


@pytest.mark.asyncio
async def test_ready_ok(client: AsyncClient) -> None:
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_503_when_db_down() -> None:
    app = create_app()

    def _unready() -> None:
        raise HTTPException(status_code=503, detail="database not ready")

    app.dependency_overrides[verify_db_ready] = _unready
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/ready")
    assert resp.status_code == 503
