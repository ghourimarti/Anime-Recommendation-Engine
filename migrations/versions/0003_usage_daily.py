"""Add usage_daily — per-user per-UTC-day usage + cost meter.

Backs the per-tenant cost meter. Composite PK (user_id, day) makes the
nightly UPSERT trivial. cost_usd is NUMERIC(12, 6) for cents-level precision
without floating-point drift across millions of small increments.

Redis is the authoritative quota-gate (fast path, sub-ms); this table is the
durable audit + cost-aggregation surface for billing, alerts, and SOC 2 evidence.

Revision ID: 0003_usage_daily
Revises:     0002_embedding_dim_1536
Create Date: 2026-06-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_usage_daily"
down_revision: str | None = "0002_embedding_dim_1536"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_daily",
        sa.Column(
            "user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("query_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    # Range queries by user (e.g. "last 30 days for user X") are the dominant
    # access pattern for billing screens. The composite PK indexes (user_id, day)
    # already, so a separate index isn't needed — but keeping the comment as
    # the place to add (day, user_id) if global-by-day reports become hot.


def downgrade() -> None:
    op.drop_table("usage_daily")
