"""Repository — the only place routes touch the ORM.

A thin data-access layer between HTTP routes and SQLAlchemy. Two payoffs:
1. Routes stay free of ORM/query details (separation of concerns).
2. Tests override `get_repository` with a fake instead of mocking SQLAlchemy
   session internals — the API layer is testable with no DB.

`user_id` is threaded as None (anonymous) for v1; auth populates it
and the same queries become per-tenant scoped.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from anime_core.db.models import Feedback, QueryHistory, UsageDaily, User
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class Repository:
    """Data access for query history + feedback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_user(self, *, user_id: str, email: str | None) -> None:
        """Idempotently mirror a Clerk user into the local users table.

        Must run before any query_history/feedback insert — those FK to users.id.
        """
        stmt = pg_insert(User).values(id=user_id, email=email)
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={"email": email})
        await self._session.execute(stmt)

    async def add_query_history(
        self, *, user_id: str | None, query: str, response: dict[str, Any]
    ) -> int:
        row = QueryHistory(user_id=user_id, query=query, response=response)
        self._session.add(row)
        await self._session.flush()  # populate row.id without ending the transaction
        return row.id

    async def list_query_history(
        self, *, user_id: str | None, limit: int, offset: int
    ) -> list[QueryHistory]:
        condition = (
            QueryHistory.user_id.is_(None) if user_id is None else QueryHistory.user_id == user_id
        )
        stmt = (
            select(QueryHistory)
            .where(condition)
            .order_by(desc(QueryHistory.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_feedback(
        self,
        *,
        user_id: str | None,
        query_history_id: int | None,
        mal_id: int,
        rating: int,
    ) -> int:
        row = Feedback(
            user_id=user_id,
            query_history_id=query_history_id,
            mal_id=mal_id,
            rating=rating,
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def record_usage(
        self,
        *,
        user_id: str,
        day: date,
        query_count_inc: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        """UPSERT-add into usage_daily. Single statement → atomic + idempotent.

        Postgres's `INSERT ... ON CONFLICT ... DO UPDATE SET col = usage_daily.col
        + EXCLUDED.col` is the one-statement atomic increment. The two-statement
        SELECT-then-UPDATE is racy under concurrent workers; this is the senior
        idiom for "add to today's rollup" in Postgres.
        """
        stmt = pg_insert(UsageDaily).values(
            user_id=user_id,
            day=day,
            query_count=query_count_inc,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "day"],
            set_={
                "query_count": UsageDaily.__table__.c.query_count + stmt.excluded.query_count,
                "input_tokens": UsageDaily.__table__.c.input_tokens + stmt.excluded.input_tokens,
                "output_tokens": UsageDaily.__table__.c.output_tokens + stmt.excluded.output_tokens,
                "cost_usd": UsageDaily.__table__.c.cost_usd + stmt.excluded.cost_usd,
            },
        )
        await self._session.execute(stmt)
