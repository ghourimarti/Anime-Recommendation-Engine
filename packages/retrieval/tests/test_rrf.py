"""Unit tests for Reciprocal Rank Fusion."""

from __future__ import annotations

from anime_core.vector_index import VectorMatch
from anime_retrieval.hybrid import reciprocal_rank_fusion
from anime_retrieval.sparse import BM25Match


def _vm(mal_id: int, chunk_index: int = 0, *, score: float = 0.5) -> VectorMatch:
    return VectorMatch(mal_id=mal_id, chunk_index=chunk_index, text=f"anime {mal_id}", score=score)


def _bm(mal_id: int, chunk_index: int = 0, *, score: float = 1.0) -> BM25Match:
    return BM25Match(mal_id=mal_id, chunk_index=chunk_index, text=f"anime {mal_id}", score=score)


def test_rrf_dense_only_returns_dense_order() -> None:
    dense = [_vm(1, score=0.9), _vm(2, score=0.7), _vm(3, score=0.5)]
    fused = reciprocal_rank_fusion(dense, [], top_k=10)
    assert [c.mal_id for c in fused] == [1, 2, 3]
    assert all(c.dense_score is not None for c in fused)
    assert all(c.sparse_score is None for c in fused)


def test_rrf_both_lists_combines_scores() -> None:
    """A doc in BOTH lists outranks a doc in only one."""
    dense = [_vm(1), _vm(2)]
    sparse = [_bm(2), _bm(3)]  # mal_id=2 is in both lists
    fused = reciprocal_rank_fusion(dense, sparse, top_k=10)
    # mal_id=2 should rank first because it appears in both lists
    assert fused[0].mal_id == 2
    assert fused[0].dense_score is not None
    assert fused[0].sparse_score is not None


def test_rrf_respects_top_k() -> None:
    dense = [_vm(i) for i in range(50)]
    fused = reciprocal_rank_fusion(dense, [], top_k=5)
    assert len(fused) == 5


def test_rrf_empty_inputs() -> None:
    assert reciprocal_rank_fusion([], []) == []
