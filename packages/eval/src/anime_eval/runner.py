"""Eval runner: run a retriever over the golden set, compute metrics, compare.

The runner is retriever-agnostic — it depends only on the `QueryRetriever`
Protocol, so it can drive the real RetrievalPipeline (live, needs DB+key) OR a
mocked retriever (unit tests). That boundary is what makes the eval logic
testable offline.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from anime_retrieval.types import Candidate

from anime_eval import metrics
from anime_eval.golden import GoldenQuery

# k values reported. final_k from the pipeline is 3, so k=1/3 are the live ones;
# k=5 is kept for when rerank_k results flow through.
DEFAULT_K_VALUES: tuple[int, ...] = (1, 3)


class QueryRetriever(Protocol):
    """Anything that turns a query into ranked Candidates. Both the real
    RetrievalPipeline and test fakes satisfy this."""

    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]: ...


@dataclass(frozen=True)
class QueryResult:
    """Per-query eval outcome."""

    id: str
    query_type: str
    retrieved_mal_ids: list[int]
    expected_mal_ids: list[int]
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalReport:
    """Aggregated eval outcome for one retriever over the golden set."""

    retriever_name: str
    per_query: list[QueryResult]
    aggregates: dict[str, float]
    adversarial: list[QueryResult]


def _score_one(
    retrieved: Sequence[int],
    expected: set[int],
    k_values: Sequence[int],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for k in k_values:
        scores[f"success@{k}"] = metrics.success_at_k(retrieved, expected, k)
        scores[f"precision@{k}"] = metrics.precision_at_k(retrieved, expected, k)
        scores[f"recall@{k}"] = metrics.recall_at_k(retrieved, expected, k)
        scores[f"ndcg@{k}"] = metrics.ndcg_at_k(retrieved, expected, k)
    scores["mrr"] = metrics.mrr(retrieved, expected)
    scores["distinct_ratio"] = metrics.distinct_ratio(retrieved)
    return scores


async def run_eval(
    retriever: QueryRetriever,
    golden: Sequence[GoldenQuery],
    *,
    retriever_name: str = "retriever",
    k_values: Sequence[int] = DEFAULT_K_VALUES,
) -> EvalReport:
    """Run `retriever` over every golden query and aggregate scored results.

    Adversarial queries (empty expected set) are scored separately — for them
    we only track distinct_ratio and what they retrieved (the refusal behavior
    is a generation-layer concern handled in the generation layer), so they never pollute the
    relevance aggregates.
    """
    scored: list[QueryResult] = []
    adversarial: list[QueryResult] = []

    for gq in golden:
        candidates = await retriever.retrieve(gq.query)
        retrieved_ids = [c.mal_id for c in candidates]
        expected = set(gq.expected_mal_ids)

        if gq.is_adversarial:
            adversarial.append(
                QueryResult(
                    id=gq.id,
                    query_type=gq.query_type,
                    retrieved_mal_ids=retrieved_ids,
                    expected_mal_ids=gq.expected_mal_ids,
                    scores={"distinct_ratio": metrics.distinct_ratio(retrieved_ids)},
                )
            )
            continue

        scored.append(
            QueryResult(
                id=gq.id,
                query_type=gq.query_type,
                retrieved_mal_ids=retrieved_ids,
                expected_mal_ids=gq.expected_mal_ids,
                scores=_score_one(retrieved_ids, expected, k_values),
            )
        )

    aggregates: dict[str, float] = {}
    if scored:
        metric_names = scored[0].scores.keys()
        for name in metric_names:
            aggregates[name] = statistics.mean(qr.scores[name] for qr in scored)

    return EvalReport(
        retriever_name=retriever_name,
        per_query=scored,
        aggregates=aggregates,
        adversarial=adversarial,
    )


def compare(baseline: EvalReport, candidate: EvalReport) -> dict[str, dict[str, float]]:
    """Return {metric: {baseline, candidate, delta}} for every shared aggregate."""
    out: dict[str, dict[str, float]] = {}
    for name in sorted(set(baseline.aggregates) | set(candidate.aggregates)):
        b = baseline.aggregates.get(name, 0.0)
        c = candidate.aggregates.get(name, 0.0)
        out[name] = {"baseline": b, "candidate": c, "delta": c - b}
    return out
