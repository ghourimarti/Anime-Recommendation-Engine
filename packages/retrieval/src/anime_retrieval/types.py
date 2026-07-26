"""Shared retrieval types.

Single immutable `Candidate` carried through every pipeline stage. Each stage
annotates with `dataclasses.replace` rather than mutating in place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    """A retrieval candidate. Score fields are populated by the stage that owns them."""

    mal_id: int
    chunk_index: int
    text: str
    # Populated by HybridRetriever:
    dense_score: float | None = None
    sparse_score: float | None = None
    hybrid_score: float | None = None
    # Populated by Reranker:
    rerank_score: float | None = None
    # Populated by mmr_select:
    mmr_score: float | None = None
    # Final 1-indexed position; assigned at the end of the pipeline.
    rank: int | None = None

    @property
    def key(self) -> tuple[int, int]:
        """(mal_id, chunk_index) — unique per chunk."""
        return (self.mal_id, self.chunk_index)
