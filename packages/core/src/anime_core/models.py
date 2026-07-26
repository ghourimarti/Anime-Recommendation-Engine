"""Pydantic domain models — the wire/contract format used across packages.

These are deliberately separate from the SQLAlchemy ORM models in
`anime_core.db.models`: domain models flow through the API and ingestion paths;
ORM models exist only inside DB sessions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Anime(BaseModel):
    """A single anime title — the unit a user gets recommended."""

    model_config = ConfigDict(frozen=True)

    mal_id: int  # MyAnimeList ID — natural key
    name: str
    score: float | None = None
    genres: list[str] = Field(default_factory=list)
    synopsis: str


class AnimeChunk(BaseModel):
    """A retrievable text chunk derived from an Anime.

    Embeddings are NOT part of this model — they live only in pgvector via
    `anime_core.db.models.AnimeChunk`. This Pydantic shape is the in-memory
    representation between the chunker and the indexer.
    """

    model_config = ConfigDict(frozen=True)

    mal_id: int
    chunk_index: int
    text: str
    metadata: dict[str, str | int | float | None] = Field(default_factory=dict)
