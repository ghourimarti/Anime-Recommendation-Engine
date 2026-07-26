"""CSV data loader for the anime corpus.

The source MAL CSV has a column literally spelled `sypnopsis` (typo in the
upstream dataset). Rather than silently rename, we surface the column name as it
is so the source-of-truth is visible — the chunker reads `Anime.synopsis` which
IS spelled correctly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from anime_core.models import Anime

REQUIRED_COLUMNS = {"MAL_ID", "Name", "Score", "Genres", "sypnopsis"}


def load_anime_csv(path: Path | str) -> list[Anime]:
    """Load and normalise the MAL anime CSV into Pydantic `Anime` objects."""
    df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df = df.dropna(subset=["Name", "sypnopsis"])

    out: list[Anime] = []
    for record in df.to_dict("records"):
        genres_raw = record.get("Genres")
        if pd.notna(genres_raw):
            genres = [g.strip() for g in str(genres_raw).split(",") if g.strip()]
        else:
            genres = []

        score_raw = record.get("Score")
        score = float(score_raw) if pd.notna(score_raw) else None

        out.append(
            Anime(
                mal_id=int(record["MAL_ID"]),
                name=str(record["Name"]).strip(),
                score=score,
                genres=genres,
                synopsis=str(record["sypnopsis"]).strip(),
            )
        )
    return out
