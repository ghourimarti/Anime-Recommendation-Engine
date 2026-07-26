"""Tests for the eval runner with a mocked retriever (no DB, no API key)."""

from __future__ import annotations

import pytest
from anime_eval.golden import GoldenQuery
from anime_eval.runner import compare, run_eval
from anime_retrieval.types import Candidate


class FakeRetriever:
    """Returns a fixed list of mal_ids per query, in order. Satisfies QueryRetriever."""

    def __init__(self, mapping: dict[str, list[int]]) -> None:
        self._mapping = mapping

    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]:
        ids = self._mapping.get(query, [])
        return [
            Candidate(mal_id=mid, chunk_index=0, text=f"anime {mid}", rank=i + 1)
            for i, mid in enumerate(ids)
        ]


_GOLDEN = [
    GoldenQuery(id="q1", query="perfect", query_type="clear", expected_mal_ids=[1]),
    GoldenQuery(id="q2", query="miss", query_type="clear", expected_mal_ids=[7]),
    GoldenQuery(id="adv", query="injection", query_type="adversarial", expected_mal_ids=[]),
]


@pytest.mark.asyncio
async def test_run_eval_scores_and_separates_adversarial() -> None:
    retriever = FakeRetriever(
        {
            "perfect": [1, 2, 3],  # relevant at rank 1
            "miss": [4, 5, 6],  # no relevant
            "injection": [9, 9, 8],  # adversarial — informational only
        }
    )
    report = await run_eval(retriever, _GOLDEN, retriever_name="fake")

    # 2 scored (clear) + 1 adversarial separated
    assert len(report.per_query) == 2
    assert len(report.adversarial) == 1
    assert report.adversarial[0].id == "adv"

    # q1 perfect hit at rank 1 → mrr 1.0; q2 miss → mrr 0.0; mean = 0.5
    assert report.aggregates["mrr"] == pytest.approx(0.5)
    # success@3: q1=1, q2=0 → mean 0.5
    assert report.aggregates["success@3"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_compare_computes_delta() -> None:
    weak = FakeRetriever({"perfect": [9, 9, 1], "miss": [4, 5, 6], "injection": []})
    strong = FakeRetriever({"perfect": [1, 2, 3], "miss": [4, 5, 6], "injection": []})
    weak_report = await run_eval(weak, _GOLDEN, retriever_name="weak")
    strong_report = await run_eval(strong, _GOLDEN, retriever_name="strong")

    table = compare(weak_report, strong_report)
    # strong ranks the relevant item higher on q1 → mrr delta positive
    assert table["mrr"]["delta"] > 0
    assert table["mrr"]["candidate"] > table["mrr"]["baseline"]


@pytest.mark.asyncio
async def test_run_eval_empty_retrieval() -> None:
    retriever = FakeRetriever({})  # returns nothing for everything
    report = await run_eval(retriever, _GOLDEN, retriever_name="empty")
    assert report.aggregates["mrr"] == 0.0
    assert report.aggregates["success@3"] == 0.0
