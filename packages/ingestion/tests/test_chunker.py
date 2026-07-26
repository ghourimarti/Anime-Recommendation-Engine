"""Unit tests for the structure-aware chunker."""

from __future__ import annotations

from anime_core.models import Anime
from anime_ingestion.chunker import TARGET_CHARS, chunk_anime


def _make_anime(
    synopsis: str,
    *,
    name: str = "Test",
    genres: list[str] | None = None,
) -> Anime:
    return Anime(
        mal_id=1,
        name=name,
        score=8.0,
        genres=genres or ["Action"],
        synopsis=synopsis,
    )


def test_short_anime_produces_one_chunk() -> None:
    anime = _make_anime("A short synopsis. Just one sentence.")
    chunks = chunk_anime(anime)
    assert len(chunks) == 1
    assert chunks[0].text.startswith("Title: Test")
    assert "Action" in chunks[0].text


def test_long_anime_produces_multiple_chunks_with_overlap() -> None:
    # Build a long synopsis: many sentences ≥ TARGET_CHARS total.
    sentences = [f"Sentence number {i} with some filler content." for i in range(200)]
    long_synopsis = " ".join(sentences)
    anime = _make_anime(long_synopsis)
    chunks = chunk_anime(anime)
    assert len(chunks) >= 2
    # Every chunk preserves the header
    for c in chunks:
        assert c.text.startswith("Title: Test")
    # No chunk grossly exceeds TARGET_CHARS (header ~50 chars + body)
    for c in chunks:
        assert len(c.text) <= TARGET_CHARS + 200


def test_chunk_metadata_includes_anime_attributes() -> None:
    anime = _make_anime("Hello world.", name="Demo", genres=["Sci-Fi", "Drama"])
    chunks = chunk_anime(anime)
    assert len(chunks) == 1
    md = chunks[0].metadata
    assert md["name"] == "Demo"
    assert md["genres_csv"] == "Sci-Fi,Drama"
    assert md["num_chunks"] == 1


def test_empty_synopsis_does_not_crash() -> None:
    anime = _make_anime("")
    chunks = chunk_anime(anime)
    # Still emits one chunk with the header
    assert len(chunks) == 1
    assert chunks[0].text.startswith("Title: Test")


def test_chunks_have_sequential_index() -> None:
    sentences = [f"Sentence {i} with content." for i in range(150)]
    long = " ".join(sentences)
    chunks = chunk_anime(_make_anime(long))
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
