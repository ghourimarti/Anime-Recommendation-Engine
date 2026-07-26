"""Unit tests for the pure IR metrics — deterministic, no I/O."""

from __future__ import annotations

import math

from anime_eval import metrics


def test_success_at_k_hit_and_miss() -> None:
    assert metrics.success_at_k([5, 9, 2], {2}, 3) == 1.0
    assert metrics.success_at_k([5, 9, 2], {2}, 2) == 0.0  # 2 is at position 3
    assert metrics.success_at_k([5, 9, 2], {99}, 3) == 0.0


def test_success_at_k_empty_expected_is_zero() -> None:
    assert metrics.success_at_k([1, 2, 3], set(), 3) == 0.0


def test_precision_at_k() -> None:
    # 2 of top-3 relevant → 2/3
    assert metrics.precision_at_k([1, 2, 9], {1, 2}, 3) == 2 / 3
    # denominator is k, not len(retrieved)
    assert metrics.precision_at_k([1], {1}, 3) == 1 / 3


def test_recall_at_k() -> None:
    # 1 of 2 expected found in top-3 → 0.5
    assert metrics.recall_at_k([1, 8, 9], {1, 5}, 3) == 0.5
    # all expected found → 1.0
    assert metrics.recall_at_k([1, 5, 9], {1, 5}, 3) == 1.0


def test_mrr_first_relevant_rank() -> None:
    assert metrics.mrr([9, 8, 1], {1}) == 1 / 3
    assert metrics.mrr([1, 8, 9], {1}) == 1.0
    assert metrics.mrr([9, 8, 7], {1}) == 0.0


def test_ndcg_perfect_and_partial() -> None:
    # Perfect ranking: relevant items first → nDCG 1.0
    assert metrics.ndcg_at_k([1, 2], {1, 2}, 2) == 1.0
    # One relevant at position 2 only, one expected → DCG=1/log2(3), IDCG=1/log2(2)=1
    expected = (1.0 / math.log2(3)) / 1.0
    assert math.isclose(metrics.ndcg_at_k([9, 1], {1}, 2), expected)


def test_ndcg_empty_expected_is_zero() -> None:
    assert metrics.ndcg_at_k([1, 2, 3], set(), 3) == 0.0


def test_distinct_ratio() -> None:
    assert metrics.distinct_ratio([1, 2, 3]) == 1.0
    assert metrics.distinct_ratio([1, 1, 2]) == 2 / 3
    assert metrics.distinct_ratio([]) == 0.0
