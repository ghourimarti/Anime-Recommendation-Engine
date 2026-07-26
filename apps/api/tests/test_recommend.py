"""POST /v1/recommend tests (structured path), with mocked service + repo."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_recommend_returns_grounded_items(client: AsyncClient, fake_repo) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post("/v1/recommend", json={"query": "psychological thriller"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "psychological thriller"
    assert body["query_history_id"] == 1
    assert body["recommendations"][0]["mal_id"] == 19
    assert body["recommendations"][0]["title"] == "Monster"
    # persisted to history
    assert len(fake_repo.added_history) == 1


@pytest.mark.asyncio
async def test_recommend_rejects_empty_query(client: AsyncClient) -> None:
    resp = await client.post("/v1/recommend", json={"query": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_recommend_rejects_missing_query(client: AsyncClient) -> None:
    resp = await client.post("/v1/recommend", json={})
    assert resp.status_code == 422
