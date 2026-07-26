"""Unit tests for Maximal Marginal Relevance."""

from __future__ import annotations

import math

from anime_retrieval.mmr import mmr_select
from anime_retrieval.types import Candidate


def _c(mal_id: int) -> Candidate:
    return Candidate(mal_id=mal_id, chunk_index=0, text=f"anime {mal_id}")


def test_mmr_empty_returns_empty() -> None:
    assert mmr_select([], [1.0, 0.0], [], k=3) == []


def test_mmr_at_lambda_1_picks_by_relevance() -> None:
    """λ=1.0 → pure relevance; expect order by cosine(D, Q)."""
    # Query aligns with x-axis; candidates' similarity ordered by their x-component.
    query = [1.0, 0.0]
    candidates = [_c(1), _c(2), _c(3)]
    embeddings = [
        [0.1, 1.0],  # least similar to query (low x)
        [0.7, 0.5],  # mid
        [1.0, 0.0],  # most similar
    ]
    selected = mmr_select(candidates, query, embeddings, k=3, lambda_=1.0)
    assert [c.mal_id for c in selected] == [3, 2, 1]


def test_mmr_at_lambda_0_picks_diverse() -> None:
    """λ=0.0 → after first pick (most relevant), prefer the most dissimilar.

    The first pick is always the most relevant. Subsequent picks at λ=0 should
    favor candidates dissimilar to already-selected.
    """
    query = [1.0, 0.0]
    candidates = [_c(1), _c(2), _c(3)]
    embeddings = [
        [1.0, 0.0],  # nearly identical to candidate 2 — should NOT be picked second
        [0.99, 0.01],  # nearly identical to candidate 1
        [0.0, 1.0],  # orthogonal — most diverse, should be picked second at λ=0
    ]
    selected = mmr_select(candidates, query, embeddings, k=2, lambda_=0.0)
    # First pick is the most relevant; second pick should be diverse (mal_id=3)
    picked_ids = [c.mal_id for c in selected]
    assert picked_ids[1] == 3, f"expected diverse pick (mal_id=3) second, got {picked_ids}"


def test_mmr_returns_at_most_k() -> None:
    query = [1.0, 0.0]
    candidates = [_c(i) for i in range(10)]
    embeddings = [[float(i), 1.0 - float(i) / 10] for i in range(10)]
    selected = mmr_select(candidates, query, embeddings, k=3)
    assert len(selected) == 3


def test_mmr_returns_all_when_k_exceeds_candidates() -> None:
    query = [1.0, 0.0]
    candidates = [_c(1), _c(2)]
    embeddings = [[1.0, 0.0], [0.5, 0.5]]
    selected = mmr_select(candidates, query, embeddings, k=10)
    assert len(selected) == 2


def test_mmr_misaligned_inputs_raises() -> None:
    try:
        mmr_select([_c(1)], [1.0, 0.0], [[1.0, 0.0], [0.5, 0.5]])
    except ValueError:
        return
    raise AssertionError("expected ValueError for misaligned inputs")


def test_mmr_lambda_out_of_range_raises() -> None:
    try:
        mmr_select([_c(1)], [1.0, 0.0], [[1.0, 0.0]], lambda_=1.5)
    except ValueError:
        return
    raise AssertionError("expected ValueError for lambda_=1.5")


def test_mmr_score_field_populated() -> None:
    query = [1.0, 0.0]
    candidates = [_c(1), _c(2)]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]
    selected = mmr_select(candidates, query, embeddings, k=2, lambda_=0.7)
    assert all(c.mmr_score is not None for c in selected)
    assert all(math.isfinite(c.mmr_score) for c in selected if c.mmr_score is not None)
