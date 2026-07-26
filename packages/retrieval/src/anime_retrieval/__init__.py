"""anime_retrieval — hybrid retrieval + cross-encoder reranker + MMR.

Public API:
    Candidate, RetrievalPipeline
    HybridRetriever, PostgresBM25Index, BgeReranker
    mmr_select, reciprocal_rank_fusion
"""

from anime_retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from anime_retrieval.mmr import mmr_select
from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.reranker import BgeReranker, Reranker
from anime_retrieval.sparse import BM25Index, BM25Match, PostgresBM25Index
from anime_retrieval.types import Candidate

__all__ = [
    "BM25Index",
    "BM25Match",
    "BgeReranker",
    "Candidate",
    "HybridRetriever",
    "PostgresBM25Index",
    "Reranker",
    "RetrievalPipeline",
    "mmr_select",
    "reciprocal_rank_fusion",
]
