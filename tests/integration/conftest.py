"""Shared fixtures for integration tests (which hit a real Postgres).

Integration tests touch the DB through the process-wide engine singleton. Because
pytest-asyncio runs each test in its own event loop, a singleton created in one
test's loop is invalid in the next test's loop. Disposing + resetting the engine
after every test makes the integration suite runnable end-to-end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.db.engine import dispose_engine


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests() -> AsyncIterator[None]:
    yield
    # Teardown runs inside the test's still-open loop → dispose cleanly, then clear
    # so the next test rebuilds a fresh engine on its own loop.
    await dispose_engine()
