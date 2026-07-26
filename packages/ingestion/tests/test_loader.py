"""Unit tests for the anime CSV loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from anime_ingestion.loader import load_anime_csv

# The MAL anime corpus shipped with the repo.
CORPUS_CSV = Path(__file__).resolve().parents[3] / "data" / "anime_with_synopsis.csv"


@pytest.mark.skipif(not CORPUS_CSV.exists(), reason=f"corpus CSV missing at {CORPUS_CSV}")
def test_load_corpus_csv_returns_anime() -> None:
    animes = load_anime_csv(CORPUS_CSV)
    assert len(animes) > 100, "Expected >100 anime in the corpus CSV"
    sample = animes[0]
    assert sample.mal_id > 0
    assert sample.name
    assert sample.synopsis
    assert isinstance(sample.genres, list)


@pytest.mark.skipif(not CORPUS_CSV.exists(), reason=f"corpus CSV missing at {CORPUS_CSV}")
def test_load_corpus_csv_genres_split_correctly() -> None:
    animes = load_anime_csv(CORPUS_CSV)
    multi_genre = [a for a in animes if len(a.genres) >= 2]
    assert multi_genre, "Expected at least one anime with multiple genres"
    assert all(isinstance(g, str) for g in multi_genre[0].genres)
    assert "" not in multi_genre[0].genres
