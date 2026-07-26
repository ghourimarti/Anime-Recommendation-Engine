"""Add account_deletions — RTBF audit table.

GDPR Art 17 erases the user's personal data, but the FACT of erasure
must be preserved for compliance evidence. This single-row-per-deletion
table is that evidence.

Schema choice — `user_id` as the PRIMARY key (not an autoincrement id):
makes the RTBF insert idempotent via `ON CONFLICT DO NOTHING`. Re-running
RTBF for an already-deleted user is a no-op, not a crash.

Revision ID: 0004_account_deletions
Revises:     0003_usage_daily
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_account_deletions"
down_revision: str | None = "0003_usage_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletions",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            comment="self_service | operator | admin_panel",
        ),
    )


def downgrade() -> None:
    op.drop_table("account_deletions")
