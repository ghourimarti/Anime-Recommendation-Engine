"""Tests for the cache primitive (NullCache + InMemoryCache)."""

from __future__ import annotations

import pytest
from anime_core.cache import InMemoryCache, NullCache


@pytest.mark.asyncio
async def test_null_cache_is_noop() -> None:
    c = NullCache()
    await c.set("k", "v")
    assert await c.get("k") is None
    assert await c.incr("n") == 0
    await c.push_capped("l", "m", max_len=5)
    assert await c.list_range("l") == []


@pytest.mark.asyncio
async def test_in_memory_get_set() -> None:
    c = InMemoryCache()
    assert await c.get("k") is None
    await c.set("k", "v")
    assert await c.get("k") == "v"


@pytest.mark.asyncio
async def test_in_memory_ttl_expiry() -> None:
    c = InMemoryCache()
    await c.set("k", "v", ttl_seconds=-1)  # already expired
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_in_memory_incr() -> None:
    c = InMemoryCache()
    assert await c.incr("n") == 1
    assert await c.incr("n") == 2


@pytest.mark.asyncio
async def test_in_memory_push_capped_lifo_and_cap() -> None:
    c = InMemoryCache()
    for i in range(5):
        await c.push_capped("l", str(i), max_len=3)
    # newest-first, capped at 3
    assert await c.list_range("l") == ["4", "3", "2"]
    assert await c.list_range("l", 0, 0) == ["4"]
