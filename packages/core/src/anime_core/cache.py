"""Cache primitive with graceful degradation.

A small string-keyed async `Cache` Protocol with three implementations:
  - NullCache:     no-op. Caching DISABLED. The whole system must work with this.
  - InMemoryCache: process-local. A real L0 tier AND the test double.
  - RedisCache:    shared cache. Every op is best-effort — a Redis error degrades
                   to a miss/no-op (never fails the request).

`get_cache()` returns NullCache when REDIS_URL is unset, so caching is opt-in and
the app never hard-depends on Redis being up.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class Cache(Protocol):
    """String-keyed async cache. Higher-level typed caches build on this."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None: ...
    async def set_nx(self, key: str, value: str, *, ttl_seconds: int) -> bool: ...
    async def delete(self, key: str) -> None: ...
    async def incr(self, key: str) -> int: ...
    async def incr_with_ttl(self, key: str, *, ttl_seconds: int) -> int: ...
    async def push_capped(self, key: str, member: str, *, max_len: int) -> None: ...
    async def list_range(self, key: str, start: int = 0, stop: int = -1) -> list[str]: ...


class NullCache:
    """No-op cache — caching disabled. Guarantees the system runs without Redis."""

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        return None

    async def set_nx(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        # Caching off → no dedup state. Return True ("treat as new / proceed") so
        # the worker still processes the message. Handlers are idempotent, so the
        # cost of a missed dedup is at-most reprocessing, never corruption.
        return True

    async def delete(self, key: str) -> None:
        return None

    async def incr(self, key: str) -> int:
        return 0

    async def incr_with_ttl(self, key: str, *, ttl_seconds: int) -> int:
        return 0

    async def push_capped(self, key: str, member: str, *, max_len: int) -> None:
        return None

    async def list_range(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        return []


class InMemoryCache:
    """Process-local cache (single-process L0 tier + the unit-test double)."""

    def __init__(self) -> None:
        # Counters live in _kv too (as stringified ints) so incr() and get() are
        # consistent — matching Redis, where INCR and GET share the key.
        self._kv: dict[str, tuple[str, float | None]] = {}
        self._lists: dict[str, list[str]] = {}

    async def get(self, key: str) -> str | None:
        item = self._kv.get(key)
        if item is None:
            return None
        value, expiry = item
        if expiry is not None and expiry < time.time():
            del self._kv[key]
            return None
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expiry = time.time() + ttl_seconds if ttl_seconds is not None else None
        self._kv[key] = (value, expiry)

    async def set_nx(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        # Set only if absent (respecting expiry). Returns True if we set it (key was
        # new), False if it already existed — the atomic dedup primitive.
        existing = await self.get(key)
        if existing is not None:
            return False
        await self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    async def delete(self, key: str) -> None:
        self._kv.pop(key, None)

    async def incr(self, key: str) -> int:
        # Increment a value stored in _kv (Redis parity: INCR + GET share the key).
        # Preserves any existing expiry.
        cur = await self.get(key)
        val = (int(cur) if cur is not None else 0) + 1
        expiry = self._kv[key][1] if key in self._kv else None
        self._kv[key] = (str(val), expiry)
        return val

    async def incr_with_ttl(self, key: str, *, ttl_seconds: int) -> int:
        # INCR, setting the TTL only on the first increment of a fresh key
        # (idiomatic INCR + EXPIRE-NX). get() honors the expiry lazily.
        cur = await self.get(key)
        if cur is None:
            self._kv[key] = ("1", time.time() + ttl_seconds)
            return 1
        val = int(cur) + 1
        expiry = self._kv[key][1]  # preserve the original TTL across increments
        self._kv[key] = (str(val), expiry)
        return val

    async def push_capped(self, key: str, member: str, *, max_len: int) -> None:
        lst = self._lists.setdefault(key, [])
        lst.insert(0, member)  # newest first (LPUSH semantics)
        del lst[max_len:]

    async def list_range(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        lst = self._lists.get(key, [])
        if stop == -1:
            return lst[start:]
        return lst[start : stop + 1]


class RedisCache:
    """Redis-backed cache. Best-effort: Redis errors degrade to miss/no-op."""

    def __init__(self, client: Redis) -> None:
        self._r = client

    async def get(self, key: str) -> str | None:
        try:
            result = await self._r.get(key)
            return None if result is None else str(result)  # decode_responses=True → str
        except Exception:  # Redis down → treat as a miss, never fail the request
            logger.warning("cache.get failed for %s; degrading to miss", key)
            return None

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        try:
            if ttl_seconds is not None:
                await self._r.set(key, value, ex=ttl_seconds)
            else:
                await self._r.set(key, value)
        except Exception:
            logger.warning("cache.set failed for %s; skipping", key)

    async def set_nx(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        # SET key value NX EX ttl — atomic "set if absent". redis-py returns True
        # when set, None when the key already existed.
        try:
            result = await self._r.set(key, value, nx=True, ex=ttl_seconds)
            return bool(result)
        except Exception:
            # Redis down → can't dedup. Return True ("proceed"): handlers are
            # idempotent, so we favor processing over silently dropping a message.
            logger.warning("cache.set_nx failed for %s; proceeding without dedup", key)
            return True

    async def delete(self, key: str) -> None:
        try:
            await self._r.delete(key)
        except Exception:
            logger.warning("cache.delete failed for %s; skipping", key)

    async def incr(self, key: str) -> int:
        try:
            return int(await self._r.incr(key))
        except Exception:
            return 0

    async def incr_with_ttl(self, key: str, *, ttl_seconds: int) -> int:
        # Atomic INCR + EXPIRE via pipeline — guarantees keys never leak even on
        # crashes between commands. EXPIRE is a no-op when the TTL already exists
        # in Redis 7+ (we'd use EXPIRE … NX to be precise, but the additional set
        # is cheap and idempotent at the seconds granularity we care about).
        try:
            async with self._r.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, ttl_seconds)
                results = await pipe.execute()
            return int(results[0])
        except Exception:
            logger.warning("cache.incr_with_ttl failed for %s; treating as 0", key)
            return 0

    async def push_capped(self, key: str, member: str, *, max_len: int) -> None:
        try:
            async with self._r.pipeline(transaction=True) as pipe:
                pipe.lpush(key, member)
                pipe.ltrim(key, 0, max_len - 1)
                await pipe.execute()
        except Exception:
            logger.warning("cache.push_capped failed for %s; skipping", key)

    async def list_range(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        try:
            return [str(x) for x in await self._r.lrange(key, start, stop)]
        except Exception:
            return []


def get_cache() -> Cache:
    """Return the configured cache. NullCache when REDIS_URL is unset (caching off)."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return NullCache()
    import redis.asyncio as aioredis

    client = aioredis.from_url(url, decode_responses=True)
    return RedisCache(client)
