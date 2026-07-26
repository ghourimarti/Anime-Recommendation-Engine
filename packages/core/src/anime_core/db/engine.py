"""Async SQLAlchemy engine + session factory.

Lazy initialization so importing this module does NOT open a DB connection —
that way `uv run pytest` works without a running postgres.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def get_database_url() -> str:
    """Read DATABASE_URL from the environment.

    Raises if unset, rather than guessing — config errors should be loud.

    postgresql+asyncpg://user:password@localhost:port/anime_db

    database type: PostgreSQL
    username: user
    password: password
    host: localhost
    port: 5432
    database name: anime_db

    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill values, "
            "or export DATABASE_URL for this shell."
        )
    return url


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def dispose_engine() -> None:
    """Dispose the engine pool and clear the cached singletons.

    Two uses:
      - Graceful API shutdown (lifespan calls this).
      - Test isolation: pytest-asyncio runs each test in a fresh event loop, but
        the cached engine binds its connection pool to the loop that created it.
        Disposing + clearing between tests lets the next test build a fresh engine
        on its own loop (avoids asyncpg 'Event loop is closed' on Windows).
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Async session context manager. Commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
