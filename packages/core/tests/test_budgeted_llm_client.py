"""Tests for BudgetedLLMClient.

Uses a fake LLMClient (the same SpyClient-style pattern as test_llm_client.py).
No network. The guard logic is pure — word count x 1.5 vs max_input_tokens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.llm_client import BudgetedLLMClient
from anime_core.resilience import BudgetExceededError
from anime_core.schemas import Recommendation, Recommendations


class FakeLLM:
    """Minimal LLMClient implementation that records calls + lets us assert non-calls."""

    def __init__(self) -> None:
        self.recommend_calls = 0
        self.stream_calls = 0

    @property
    def model(self) -> str:
        return "fake-model"

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self.recommend_calls += 1
        return Recommendations(
            items=[Recommendation(mal_id=1, title="t", summary="s", why_match="w")]
        )

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        self.stream_calls += 1
        for token in ["a", "b"]:
            yield token


def _budgeted(inner: FakeLLM, *, max_input_tokens: int = 100) -> BudgetedLLMClient:
    return BudgetedLLMClient(inner=inner, max_input_tokens=max_input_tokens, max_output_tokens=512)


@pytest.mark.asyncio
async def test_within_budget_delegates_to_inner() -> None:
    inner = FakeLLM()
    result = await _budgeted(inner, max_input_tokens=100).recommend(query="short", context="ctx")
    assert result.items[0].title == "t"
    assert inner.recommend_calls == 1


@pytest.mark.asyncio
async def test_oversized_input_raises_budget_exceeded() -> None:
    inner = FakeLLM()
    # 200 words x 1.5 ~ 300 estimated tokens, well over the 100 budget.
    huge = " ".join(["word"] * 200)
    with pytest.raises(BudgetExceededError):
        await _budgeted(inner, max_input_tokens=100).recommend(query=huge, context="")
    # The provider must NOT have been called — the whole point of a pre-call guard.
    assert inner.recommend_calls == 0


@pytest.mark.asyncio
async def test_oversized_context_also_blocked() -> None:
    """The guard counts BOTH query and context — context is usually the larger
    contributor (retrieved candidates), so leaving it out would defeat the cap."""
    inner = FakeLLM()
    huge_context = " ".join(["chunk"] * 200)
    with pytest.raises(BudgetExceededError):
        await _budgeted(inner, max_input_tokens=100).recommend(query="short", context=huge_context)
    assert inner.recommend_calls == 0


@pytest.mark.asyncio
async def test_stream_also_guarded() -> None:
    inner = FakeLLM()
    huge = " ".join(["word"] * 200)
    with pytest.raises(BudgetExceededError):
        async for _ in _budgeted(inner, max_input_tokens=100).astream(query=huge, context=""):
            pass
    assert inner.stream_calls == 0


@pytest.mark.asyncio
async def test_stream_passes_through_when_under_budget() -> None:
    inner = FakeLLM()
    out = [t async for t in _budgeted(inner, max_input_tokens=100).astream(query="q", context="c")]
    assert out == ["a", "b"]


def test_exposes_max_input_and_output_tokens() -> None:
    client = BudgetedLLMClient(inner=FakeLLM(), max_input_tokens=600, max_output_tokens=1200)
    assert client.max_input_tokens == 600
    assert client.max_output_tokens == 1200
    # Model name passes through.
    assert client.model == "fake-model"
