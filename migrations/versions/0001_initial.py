"""Initial schema: users, anime_titles, anime_chunks, query_history, feedback.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Match anime_core.db.models.EMBEDDING_DIM (OpenAI text-embedding-3-large).
EMBEDDING_DIM = 3072


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "anime_titles",
        # mal_id is MyAnimeList's natural key — never auto-generated.
        sa.Column("mal_id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("genres", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("synopsis", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "anime_chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "mal_id",
            sa.BigInteger,
            sa.ForeignKey("anime_titles.mal_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("chunk_metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_anime_chunks_mal_id", "anime_chunks", ["mal_id"])

    # tsvector column for hybrid search — used for BM25-like sparse retrieval.
    op.execute(
        """
        ALTER TABLE anime_chunks
        ADD COLUMN text_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
        """
    )
    op.execute("CREATE INDEX ix_anime_chunks_text_tsv ON anime_chunks USING gin(text_tsv)")

    op.create_table(
        "query_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("response", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_query_history_user_id_created_at",
        "query_history",
        ["user_id", "created_at"],
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "query_history_id",
            sa.BigInteger,
            sa.ForeignKey("query_history.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("mal_id", sa.BigInteger, nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_index("ix_query_history_user_id_created_at", table_name="query_history")
    op.drop_table("query_history")
    op.drop_index("ix_anime_chunks_text_tsv", table_name="anime_chunks")
    op.execute("ALTER TABLE anime_chunks DROP COLUMN text_tsv")
    op.drop_index("ix_anime_chunks_mal_id", table_name="anime_chunks")
    op.drop_table("anime_chunks")
    op.drop_table("anime_titles")
    op.drop_table("users")
