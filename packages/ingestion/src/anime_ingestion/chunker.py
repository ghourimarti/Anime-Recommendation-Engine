"""Structure-aware chunker.

Design goals (a naive fixed-size character splitter fails all four):

1. Splits on sentence boundaries (never mid-word, rarely mid-sentence).
2. Preserves a structured header (Title + Genres) on every chunk so the embedding
   sees the title/genres alongside the synopsis text — helps the embedding model
   anchor on what makes the anime distinct.
3. Honours an overlap budget (~15%) so context isn't lost at chunk boundaries.
4. Carries rich metadata (name, score, genres_csv, num_chunks).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from anime_core.models import Anime, AnimeChunk

# Rough heuristic: 1 token ≈ 4 chars for English text.
# Target ~500 tokens per chunk with ~75-token overlap (15%).
TARGET_CHARS = 2000
OVERLAP_CHARS = 300


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _pack_sentences(sentences: Iterable[str]) -> list[str]:
    """Greedy-pack sentences into chunks ≤ TARGET_CHARS with OVERLAP_CHARS overlap.

    The overlap is the tail of the previous chunk re-included at the start of the
    next chunk, in whole sentences only (never mid-sentence).
    """
    sentence_list = list(sentences)
    chunks: list[str] = []
    buf: list[str] = []
    size = 0

    for s in sentence_list:
        if size + len(s) + 1 > TARGET_CHARS and buf:
            chunks.append(" ".join(buf))
            # Build overlap from the tail of buf.
            overlap: list[str] = []
            osize = 0
            for t in reversed(buf):
                if osize + len(t) + 1 > OVERLAP_CHARS:
                    break
                overlap.insert(0, t)
                osize += len(t) + 1
            buf = overlap
            size = osize
        buf.append(s)
        size += len(s) + 1

    if buf:
        chunks.append(" ".join(buf))
    return chunks


def chunk_anime(anime: Anime) -> list[AnimeChunk]:
    """Produce one or more chunks for an anime.

    The text we embed is the synopsis prefixed by a structured header so the
    embedding sees the title/genres (helps lexical+semantic alignment).
    """
    genres_str = ", ".join(anime.genres) if anime.genres else "unknown"
    header = f"Title: {anime.name}\nGenres: {genres_str}\n\n"
    body = anime.synopsis or ""

    sentences = _split_sentences(body)
    pieces = _pack_sentences(sentences) if sentences else [body[:TARGET_CHARS]]

    chunks: list[AnimeChunk] = []
    for idx, piece in enumerate(pieces):
        text = header + piece
        chunks.append(
            AnimeChunk(
                mal_id=anime.mal_id,
                chunk_index=idx,
                text=text,
                metadata={
                    "name": anime.name,
                    "score": anime.score,
                    "genres_csv": ",".join(anime.genres),
                    "num_chunks": len(pieces),
                },
            )
        )
    return chunks
