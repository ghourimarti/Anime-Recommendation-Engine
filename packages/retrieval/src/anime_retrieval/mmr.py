"""Maximal Marginal Relevance (MMR) diversifier.

MMR picks k items maximizing:

    MMR(D) = λ * sim(D, Q) - (1 - λ) * max_j sim(D, D_j)

where the max is over already-selected items. λ controls the
relevance/diversity trade-off:

    λ = 1.0 → relevance-only (pick top-k by similarity to Q)
    λ = 0.0 → diversity-only (pick most dissimilar to already-selected)

the default λ is 0.7 — favor relevance but punish near-duplicates.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from anime_retrieval.types import Candidate


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize rows of a 2-D array (no-op safe on zero rows)."""
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def mmr_select(
    candidates: list[Candidate],
    query_embedding: list[float],
    candidate_embeddings: list[list[float]],
    *,
    k: int = 3,
    lambda_: float = 0.7,
) -> list[Candidate]:
    """Pick `k` candidates via MMR. Returned in MMR-selection order.

    `candidates[i]` and `candidate_embeddings[i]` must align.
    """
    if not candidates:
        return []
    if len(candidates) != len(candidate_embeddings):
        raise ValueError(
            f"candidates ({len(candidates)}) and candidate_embeddings "
            f"({len(candidate_embeddings)}) must align"
        )
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError(f"lambda_ must be in [0, 1], got {lambda_}")

    embeddings = _normalize(np.asarray(candidate_embeddings, dtype=np.float32))
    query_n = np.asarray(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_n)
    if query_norm > 0:
        query_n = query_n / query_norm

    relevance = (embeddings @ query_n).astype(np.float32)

    n = len(candidates)
    selected: list[int] = []
    mmr_scores: dict[int, float] = {}
    remaining = list(range(n))

    while remaining and len(selected) < k:
        best_idx = -1
        best_mmr = -math.inf
        for i in remaining:
            rel = float(relevance[i])
            if not selected:
                mmr = rel
            else:
                sims_to_selected = embeddings[selected] @ embeddings[i]
                max_sim = float(sims_to_selected.max())
                mmr = lambda_ * rel - (1.0 - lambda_) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        if best_idx < 0:
            break
        selected.append(best_idx)
        remaining.remove(best_idx)
        mmr_scores[best_idx] = best_mmr

    return [dataclasses.replace(candidates[i], mmr_score=mmr_scores[i]) for i in selected]
