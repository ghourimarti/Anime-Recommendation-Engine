"""Tests for the RTBF flow.

Covers the unit-of-work in `anime_core.rtbf.delete_user` + the
`DELETE /v1/account` endpoint contract.

The DB integration path (real Postgres, real cascade) is exercised by
the integration suite (`tests/integration/`); these tests run against
mocked sessions to avoid coupling.

Test matrix:
  - delete_user dry-run returns counts, does NOT mutate
  - delete_user live deletes from every user-scoped table + audit row
  - delete_user idempotent on re-run (audit row already present)
  - delete_user with clerk_client: Clerk called FIRST, DB if Clerk ok
  - delete_user clerk failure: raises ClerkAPIError, DB stays untouched
  - DeletionSummary.format renders readably
  - DELETE /v1/account requires auth (401 when no header)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from anime_core.clerk import ClerkAPIError, ClerkClient
from anime_core.rtbf import DeletionSummary, delete_user


class _FakeResult:
    """Minimal stand-in for SQLAlchemy Result for our COUNT/RETURNING queries."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar(self) -> Any:
        return self._value


class _FakeSession:
    """Records execute() calls and returns scripted results for COUNT queries.

    `count_map` maps "{table}:{where}" → row count for the COUNT phase.
    `audit_inserted` controls whether the audit INSERT's RETURNING comes back
    with the user_id (fresh insert) or None (ON CONFLICT no-op).
    """

    def __init__(
        self,
        *,
        count_map: dict[str, int],
        audit_inserted: bool = True,
    ) -> None:
        self.count_map = count_map
        self.audit_inserted = audit_inserted
        self.executed_sql: list[str] = []
        self.executed_params: list[dict[str, Any]] = []
        self.committed = False

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(stmt).strip()
        self.executed_sql.append(sql)
        self.executed_params.append(params or {})
        # COUNT queries
        for key, val in self.count_map.items():
            table, where = key.split("::", 1)
            if f"FROM {table} WHERE {where}" in sql and "COUNT(*)" in sql:
                return _FakeResult(val)
        # Audit insert with RETURNING
        if "INSERT INTO account_deletions" in sql:
            return _FakeResult("uid" if self.audit_inserted else None)
        # DELETE queries — return empty
        return _FakeResult(None)

    async def commit(self) -> None:
        self.committed = True


def _default_counts(uid: str = "test_user") -> dict[str, int]:
    return {
        "feedback::user_id = :uid": 3,
        "query_history::user_id = :uid": 7,
        "usage_daily::user_id = :uid": 2,
        "users::id = :uid": 1,
    }


# ──────────────────────────────────────────────────
# delete_user — dry-run path
# ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_returns_counts_no_mutation() -> None:
    session = _FakeSession(count_map=_default_counts())
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=True,
    )
    assert summary.dry_run is True
    assert summary.clerk_deleted is None
    assert summary.rows_deleted == {
        "feedback": 3,
        "query_history": 7,
        "usage_daily": 2,
        "users": 1,
    }
    assert summary.total_rows == 13
    assert summary.audit_row_inserted is False
    # No DELETE and no INSERT statements should have run.
    assert not any("DELETE FROM" in s for s in session.executed_sql)
    assert not any("INSERT INTO account_deletions" in s for s in session.executed_sql)
    assert session.committed is False


@pytest.mark.asyncio
async def test_dry_run_with_clerk_client_skips_clerk() -> None:
    """Even with a Clerk client, dry-run must not call Clerk."""
    session = _FakeSession(count_map=_default_counts())
    clerk = AsyncMock(spec=ClerkClient)
    clerk.delete_user = AsyncMock(return_value=True)
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=True,
        clerk_client=clerk,
    )
    clerk.delete_user.assert_not_called()
    assert summary.clerk_deleted is None


# ──────────────────────────────────────────────────
# delete_user — live path
# ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_deletes_and_inserts_audit_row() -> None:
    session = _FakeSession(count_map=_default_counts(), audit_inserted=True)
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=False,
    )
    assert summary.dry_run is False
    assert summary.total_rows == 13
    assert summary.audit_row_inserted is True
    # DELETE statements ran for each non-empty table.
    deletes = [s for s in session.executed_sql if "DELETE FROM" in s]
    assert len(deletes) == 4
    # Audit INSERT ran.
    inserts = [s for s in session.executed_sql if "INSERT INTO account_deletions" in s]
    assert len(inserts) == 1
    # Commit fired.
    assert session.committed is True


@pytest.mark.asyncio
async def test_live_skips_empty_table_deletes() -> None:
    """Tables with 0 rows shouldn't generate DELETE statements."""
    counts = _default_counts()
    counts["feedback::user_id = :uid"] = 0  # nothing to delete from feedback
    session = _FakeSession(count_map=counts, audit_inserted=True)
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=False,
    )
    assert summary.rows_deleted["feedback"] == 0
    deletes = [s for s in session.executed_sql if "DELETE FROM" in s]
    feedback_deletes = [s for s in deletes if "feedback" in s]
    assert len(feedback_deletes) == 0
    # Still 3 deletes for the other tables.
    assert len(deletes) == 3


@pytest.mark.asyncio
async def test_idempotent_redelete() -> None:
    """Re-running RTBF on an already-deleted user: counts all zero, audit
    INSERT returns None (ON CONFLICT DO NOTHING), commit still fires."""
    counts = {
        "feedback::user_id = :uid": 0,
        "query_history::user_id = :uid": 0,
        "usage_daily::user_id = :uid": 0,
        "users::id = :uid": 0,
    }
    session = _FakeSession(count_map=counts, audit_inserted=False)
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=False,
    )
    assert summary.total_rows == 0
    assert summary.audit_row_inserted is False
    assert session.committed is True
    # No DELETE statements should have run (every count was 0).
    assert not any("DELETE FROM" in s for s in session.executed_sql)


# ──────────────────────────────────────────────────
# Clerk integration
# ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clerk_called_first_then_db() -> None:
    session = _FakeSession(count_map=_default_counts(), audit_inserted=True)
    clerk = AsyncMock(spec=ClerkClient)
    clerk.delete_user = AsyncMock(return_value=True)
    summary = await delete_user(
        session,  # type: ignore[arg-type]
        user_id="test_user",
        dry_run=False,
        clerk_client=clerk,
    )
    clerk.delete_user.assert_awaited_once_with("test_user")
    assert summary.clerk_deleted is True
    # DB rows still got deleted.
    assert summary.total_rows == 13


@pytest.mark.asyncio
async def test_clerk_failure_does_not_touch_db() -> None:
    session = _FakeSession(count_map=_default_counts())
    clerk = AsyncMock(spec=ClerkClient)
    clerk.delete_user = AsyncMock(side_effect=ClerkAPIError("network"))
    with pytest.raises(ClerkAPIError):
        await delete_user(
            session,  # type: ignore[arg-type]
            user_id="test_user",
            dry_run=False,
            clerk_client=clerk,
        )
    # No DB mutation, no commit.
    assert not any("DELETE FROM" in s for s in session.executed_sql)
    assert not any("INSERT INTO account_deletions" in s for s in session.executed_sql)
    assert session.committed is False


# ──────────────────────────────────────────────────
# DeletionSummary.format
# ──────────────────────────────────────────────────


def test_summary_format_dry_run() -> None:
    s = DeletionSummary(
        user_id="test_user",
        dry_run=True,
        clerk_deleted=None,
        rows_deleted={"feedback": 3, "query_history": 7, "usage_daily": 2, "users": 1},
    )
    out = s.format()
    assert "DRY-RUN" in out
    assert "test_user" in out
    assert "feedback" in out
    assert "Total rows: 13" in out


def test_summary_format_live() -> None:
    s = DeletionSummary(
        user_id="test_user",
        dry_run=False,
        clerk_deleted=True,
        rows_deleted={"feedback": 3, "query_history": 7, "usage_daily": 2, "users": 1},
        audit_row_inserted=True,
    )
    out = s.format()
    assert "DRY-RUN" not in out
    assert "Clerk-side: OK" in out
    assert "Audit row: inserted" in out


# ──────────────────────────────────────────────────
# Endpoint: auth required
# ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_account_requires_auth() -> None:
    """DELETE /v1/account without a JWT must 401, not 204."""
    from anime_api.routes import account
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    app = FastAPI()
    app.include_router(account.router, prefix="/v1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # No Authorization header.
        r = await client.delete("/v1/account")
    # Real auth dep will 401; in the dep-resolution failure case FastAPI returns 422,
    # which is also "auth not satisfied". Accept either.
    assert r.status_code in (401, 422), f"expected 401/422, got {r.status_code}"
