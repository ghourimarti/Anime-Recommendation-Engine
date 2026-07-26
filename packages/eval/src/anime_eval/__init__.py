"""anime_eval — golden sets, deterministic IR metrics, RAGAS wiring, A/B runner.

Public API:
    GoldenQuery, load_golden_set
    metrics (module: success_at_k, precision_at_k, recall_at_k, mrr, ndcg_at_k, ...)
    QueryRetriever, QueryResult, EvalReport, run_eval, compare
    NaiveRetriever
"""

from anime_eval import metrics
from anime_eval.baseline import NaiveRetriever
from anime_eval.golden import GoldenQuery, load_golden_set
from anime_eval.runner import EvalReport, QueryResult, QueryRetriever, compare, run_eval

__all__ = [
    "EvalReport",
    "GoldenQuery",
    "NaiveRetriever",
    "QueryResult",
    "QueryRetriever",
    "compare",
    "load_golden_set",
    "metrics",
    "run_eval",
]
