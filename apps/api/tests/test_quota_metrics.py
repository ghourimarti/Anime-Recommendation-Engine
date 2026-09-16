"""A 429 must be attributable (Track O.4).

The HTTP metrics already show 429s; they do not show WHY. "The free-tier cap is
now the product's ceiling" and "one client is hammering us" look identical in a
status-code chart and call for opposite responses, so the refusal is recorded
with its scope.

Calls the dependency directly rather than going through the app fixture: this is
about the quota path, and nothing here needs a running application.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from anime_api import quota as quota_mod
from anime_api.quota import enforce_quota
from fastapi import HTTPException


class FakeCounter:
    def __init__(self, *, over_limit: bool) -> None:
        self._over = over_limit

    async def incr_and_check(self, *, user_id, limit, now):  # type: ignore[no-untyped-def]
        return SimpleNamespace(over_limit=self._over, retry_after_seconds=42)


@pytest.fixture
def rejections(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(quota_mod, "record_quota_rejection", lambda **kw: calls.append(kw))
    return calls


USER = SimpleNamespace(id="user_123", email="someone@example.com")
SETTINGS = SimpleNamespace(quota_free_tier_daily=50)


@pytest.mark.asyncio
async def test_refusal_is_recorded_with_its_scope(rejections: list[dict]) -> None:
    with pytest.raises(HTTPException) as exc:
        await enforce_quota(
            user=USER,  # type: ignore[arg-type]
            counter=FakeCounter(over_limit=True),  # type: ignore[arg-type]
            settings=SETTINGS,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "42"}
    assert rejections == [{"scope": "user_daily"}]


@pytest.mark.asyncio
async def test_allowed_request_records_nothing(rejections: list[dict]) -> None:
    await enforce_quota(
        user=USER,  # type: ignore[arg-type]
        counter=FakeCounter(over_limit=False),  # type: ignore[arg-type]
        settings=SETTINGS,  # type: ignore[arg-type]
    )
    assert rejections == []
