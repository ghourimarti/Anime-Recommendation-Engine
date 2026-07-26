"""Feedback + history endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_feedback_recorded(client: AsyncClient, fake_repo) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post(
        "/v1/feedback", json={"query_history_id": 1, "mal_id": 19, "rating": 1}
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": 7, "status": "recorded"}
    assert fake_repo.added_feedback == [{"mal_id": 19, "rating": 1}]


@pytest.mark.asyncio
async def test_feedback_rejects_bad_rating(client: AsyncClient) -> None:
    resp = await client.post("/v1/feedback", json={"mal_id": 19, "rating": 2})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_history_returns_items(client: AsyncClient) -> None:
    resp = await client.get("/v1/history?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 10
    assert body["items"][0]["query"] == "psychological thriller"
    assert body["items"][0]["recommendations"][0]["mal_id"] == 19


@pytest.mark.asyncio
async def test_history_rejects_bad_limit(client: AsyncClient) -> None:
    resp = await client.get("/v1/history?limit=0")
    assert resp.status_code == 422
