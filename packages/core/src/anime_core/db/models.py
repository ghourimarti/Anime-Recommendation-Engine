"""SQLAlchemy 2.0 ORM models.

These define the on-disk schema. Pydantic equivalents for wire format live in
`anime_core.models`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# pgvector dimension for OpenAI `text-embedding-3-small` — revised 2026-05-27.
EMBEDDING_DIM = 1536


class Base(DeclarativeBase):
    """Common declarative base for all ORM models."""


class User(Base):
    """End-user account. Clerk owns identity; this table is the local mirror."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # Clerk user_id
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AnimeTitle(Base):
    """A canonical anime entry (the user-facing entity for recommendations)."""

    __tablename__ = "anime_titles"

    # mal_id is MyAnimeList's natural key — externally assigned, never auto-generated.
    mal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list[AnimeChunk]] = relationship(
        back_populates="anime",
        cascade="all, delete-orphan",
    )


class AnimeChunk(Base):
    """A retrievable chunk of an anime with its OpenAI embedding."""

    __tablename__ = "anime_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("anime_titles.mal_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    anime: Mapped[AnimeTitle] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_anime_chunks_mal_id", "mal_id"),)


class QueryHistory(Base):
    """Per-user query log. Populated by the API by the API."""

    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_query_history_user_id_created_at", "user_id", "created_at"),)


class Feedback(Base):
    """Per-recommendation thumbs feedback. Populated by the frontend."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="SET NULL")
    )
    query_history_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("query_history.id", ondelete="CASCADE")
    )
    mal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = up, -1 = down
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UsageDaily(Base):
    """Per-user per-UTC-day usage rollup — the durable record behind the quota gate.

    Redis is the request-gate (fast path, authoritative for the 429 decision).
    This table is the audit trail + cost meter — written via UPSERT after every
    successful LLM call, so per-tenant cost is queryable for billing/quotas/SOC2.

    `day` is a DATE (not DateTime): one row per user per UTC calendar day. The
    composite primary key (user_id, day) makes the UPSERT trivial and prevents
    duplicate-row anomalies even under concurrent writes from multiple workers.

    `cost_usd` is NUMERIC(12,6) — six-decimal precision avoids float accumulation
    drift across millions of small per-request increments. BigInt micros would be
    even more correct but loses the ergonomics of `Decimal` arithmetic.
    """

    __tablename__ = "usage_daily"

    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
