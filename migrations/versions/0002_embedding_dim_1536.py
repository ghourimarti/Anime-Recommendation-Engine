"""Resize embedding column: vector(3072) → vector(1536).

Switches the embedding model from text-embedding-3-large (3072-dim) to
text-embedding-3-small (1536-dim) to bring per-query embedding p50 under the
300 ms latency gate at a fraction of the cost, with negligible recall loss on
this corpus.

pgvector does not support ALTER COLUMN … TYPE for a dimension change, so we
drop and recreate the column. All existing rows are deleted (the column becomes
nullable until the next `make ingest` run, which re-populates via upsert).
This is intentional: re-running ingest is required after this migration.

Revision ID: 0002_embedding_dim_1536
Revises:     0001_initial
Create Date: 2026-05-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0002_embedding_dim_1536"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DIM = 3072
NEW_DIM = 1536


def upgrade() -> None:
    # Truncate existing embeddings — they were produced by 3-large and are
    # incompatible with the 3-small vector space.
    op.execute("TRUNCATE TABLE anime_chunks CASCADE")

    op.drop_column("anime_chunks", "embedding")
    op.add_column(
        "anime_chunks",
        sa.Column("embedding", Vector(NEW_DIM), nullable=True),
    )


def downgrade() -> None:
    op.execute("TRUNCATE TABLE anime_chunks CASCADE")

    op.drop_column("anime_chunks", "embedding")
    op.add_column(
        "anime_chunks",
        sa.Column("embedding", Vector(OLD_DIM), nullable=True),
    )
