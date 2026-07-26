"""RAGAS wiring — LLM-judge retrieval metrics (context precision/recall).

RAGAS is an OPTIONAL extra (it pulls heavy deps and needs an OpenAI key to run
its LLM judge). Install with:

    uv sync --extra ragas

These metrics cost money (LLM-judge calls), so they are never part of the free
CI gate — the deterministic IR metrics in `metrics.py` are. RAGAS is for the
deeper, periodic quality read. The generation-side metrics (faithfulness,
answer_relevancy) are intentionally NOT wired here yet — there is no generated
answer until the LLM chain exists; they get added then.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from anime_eval.golden import GoldenQuery
from anime_eval.runner import QueryRetriever


@dataclass(frozen=True)
class RagasResult:
    """Aggregated RAGAS scores over the evaluated queries."""

    context_precision: float
    context_recall: float
    n_queries: int


def _require_ragas() -> None:
    try:
        import ragas  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "RAGAS is not installed. Install the optional extra:\n"
            "    uv sync --extra ragas\n"
            "and ensure OPENAI_API_KEY is set (RAGAS uses an LLM judge)."
        ) from exc


async def run_ragas_eval(
    retriever: QueryRetriever,
    golden: Sequence[GoldenQuery],
) -> RagasResult:
    """Score retrieval quality with RAGAS context-precision/recall (LLM judge).

    Live-only: requires the `ragas` extra + OPENAI_API_KEY. Adversarial queries
    are skipped (no ground-truth contexts to judge against).
    """
    _require_ragas()

    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall

    questions: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []

    for gq in golden:
        if gq.is_adversarial:
            continue
        candidates = await retriever.retrieve(gq.query)
        questions.append(gq.query)
        contexts.append([c.text for c in candidates])
        # RAGAS context_recall needs a reference answer; the notes field (the
        # canonical titles) is a serviceable ground-truth reference here.
        ground_truths.append(gq.notes or " ".join(map(str, gq.expected_mal_ids)))

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )
    result = evaluate(dataset, metrics=[context_precision, context_recall])
    scores = result.to_pandas()
    return RagasResult(
        context_precision=float(scores["context_precision"].mean()),
        context_recall=float(scores["context_recall"].mean()),
        n_queries=len(questions),
    )
