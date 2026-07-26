"""Pure information-retrieval metrics — deterministic, no LLM, no I/O.

All functions take an ordered list of retrieved mal_ids and a set of expected
(relevant) mal_ids. Because they are pure, they are trivially unit-testable and
run for free in CI — this is the gate that answers the embedding-model question (does the
smaller embedding model hurt retrieval?) without spending a cent on API calls.

Why several metrics instead of one:
  - success@k (hit rate): did ANY relevant item appear in the top-k? Best signal
    for franchise/edge queries where |expected| is large.
  - precision@k: of the k returned, how many are relevant? Best when the user
    wants a tight, all-relevant result set.
  - recall@k: of all relevant items, how many did we surface in top-k? Best for
    clear single-target queries; misleading when |expected| > k.
  - mrr: how high did the FIRST relevant item rank? Rewards getting one right fast.
  - ndcg@k: rank-weighted relevance; the academic standard.
No single metric is right for every query shape, so the runner reports all of
them and the analysis picks the appropriate lens per query_type.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _top_k(retrieved: Sequence[int], k: int) -> list[int]:
    return list(retrieved[:k])


def success_at_k(retrieved: Sequence[int], expected: set[int], k: int) -> float:
    """1.0 if any relevant item is in the top-k, else 0.0 (a.k.a. hit rate)."""
    if not expected:
        return 0.0
    return 1.0 if any(mal_id in expected for mal_id in _top_k(retrieved, k)) else 0.0


def precision_at_k(retrieved: Sequence[int], expected: set[int], k: int) -> float:
    """Fraction of the top-k that are relevant. Denominator is k (not len(top_k))."""
    if k <= 0:
        return 0.0
    hits = sum(1 for mal_id in _top_k(retrieved, k) if mal_id in expected)
    return hits / k


def recall_at_k(retrieved: Sequence[int], expected: set[int], k: int) -> float:
    """Fraction of all relevant items that appear in the top-k."""
    if not expected:
        return 0.0
    hits = sum(1 for mal_id in _top_k(retrieved, k) if mal_id in expected)
    return hits / len(expected)


def mrr(retrieved: Sequence[int], expected: set[int]) -> float:
    """Reciprocal rank of the first relevant item (0.0 if none retrieved)."""
    if not expected:
        return 0.0
    for rank, mal_id in enumerate(retrieved, start=1):
        if mal_id in expected:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[int], expected: set[int], k: int) -> float:
    """Binary-relevance normalized discounted cumulative gain at k."""
    if not expected:
        return 0.0
    dcg = 0.0
    for i, mal_id in enumerate(_top_k(retrieved, k), start=1):
        if mal_id in expected:
            dcg += 1.0 / math.log2(i + 1)
    ideal_hits = min(k, len(expected))
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def distinct_ratio(retrieved: Sequence[int]) -> float:
    """Fraction of retrieved items that are distinct (1.0 == no duplicate anime)."""
    if not retrieved:
        return 0.0
    return len(set(retrieved)) / len(retrieved)
