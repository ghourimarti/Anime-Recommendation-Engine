"""Handler unit tests — fakes for cache + DB session, no real infra."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from anime_core.cache import InMemoryCache
from anime_worker.handlers.base import HandlerContext
from anime_worker.handlers.feedback import (
    FEEDBACK_COUNT_KEY,
    REVIEW_QUEUE_KEY,
    handle_feedback_recorded,
)
from anime_worker.handlers.gdpr_delete import handle_gdpr_delete
from anime_worker.handlers.housekeeping import POPULAR_KEY, handle_popular_precompute
from anime_worker.handlers.reembed import handle_reembed_corpus


# ─── feedback (cache-only) ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_feedback_thumbs_down_queues_review() -> None:
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    await handle_feedback_recorded({"rating": -1, "mal_id": 19, "query_history_id": 7}, ctx)
    assert await cache.get(FEEDBACK_COUNT_KEY) == "1"
    queued = await cache.list_range(REVIEW_QUEUE_KEY, 0, -1)
    assert json.loads(queued[0])["mal_id"] == 19


@pytest.mark.asyncio
async def test_feedback_thumbs_up_counts_only() -> None:
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    await handle_feedback_recorded({"rating": 1, "mal_id": 1}, ctx)
    assert await cache.get(FEEDBACK_COUNT_KEY) == "1"
    assert await cache.list_range(REVIEW_QUEUE_KEY, 0, -1) == []


# ─── fake DB session plumbing ────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []
        self.executed: list[Any] = []

    async def execute(self, stmt: Any) -> _FakeResult:
        self.executed.append(stmt)
        return _FakeResult(self._rows)


def _factory(session: _FakeSession) -> Any:
    @asynccontextmanager
    async def _f() -> Any:
        yield session

    return _f


class _Row:
    def __init__(self, mal_id: int) -> None:
        self.mal_id = mal_id


# ─── housekeeping ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_popular_precompute_writes_redis() -> None:
    cache = InMemoryCache()
    session = _FakeSession(rows=[_Row(21), _Row(19), _Row(1)])
    ctx = HandlerContext(cache=cache, session_factory=_factory(session))
    await handle_popular_precompute({}, ctx)
    assert json.loads(await cache.get(POPULAR_KEY)) == [21, 19, 1]


# ─── gdpr delete ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gdpr_delete_issues_four_deletes() -> None:
    session = _FakeSession()
    ctx = HandlerContext(cache=InMemoryCache(), session_factory=_factory(session))
    await handle_gdpr_delete({"user_id": "user_x"}, ctx)
    # feedback, query_history, usage_daily, users — explicit deletes, not FK SET NULL.
    assert len(session.executed) == 4


@pytest.mark.asyncio
async def test_gdpr_delete_requires_user_id() -> None:
    ctx = HandlerContext(cache=InMemoryCache(), session_factory=_factory(_FakeSession()))
    with pytest.raises(ValueError, match="user_id"):
        await handle_gdpr_delete({}, ctx)


# ─── reembed (injected ingest) ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reembed_calls_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    session = _FakeSession()
    ctx = HandlerContext(cache=InMemoryCache(), session_factory=_factory(session))
    calls: list[Any] = []

    async def fake_ingest(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["csv_path"])
        return {"anime_count": 1}

    await handle_reembed_corpus(
        {"csv_path": "data/anime_with_synopsis.csv"}, ctx, ingest_fn=fake_ingest
    )
    assert calls == ["data/anime_with_synopsis.csv"]


@pytest.mark.asyncio
async def test_reembed_requires_csv_path() -> None:
    ctx = HandlerContext(cache=InMemoryCache(), session_factory=_factory(_FakeSession()))
    with pytest.raises(ValueError, match="csv_path"):
        await handle_reembed_corpus({}, ctx, ingest_fn=lambda **k: None)  # type: ignore[arg-type]
