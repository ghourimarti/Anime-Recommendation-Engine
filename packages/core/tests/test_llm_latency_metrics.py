"""Per-provider LLM latency and TTFT must be recorded at the shared call site.

Every provider — the self-hosted vLLM/SGLang venue, Groq and OpenAI — reaches the
network through _LangChainClient, so instrumenting it once covers all four. These
tests pin that: a regression here would leave the per-provider dashboard rows
silently empty, which reads as "this provider was never used" rather than "the
measurement broke".
"""

from __future__ import annotations

import pytest
from anime_core import llm_client as llm_mod
from anime_core.llm_client import _LangChainClient
from anime_core.schemas import Recommendation, Recommendations
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

RECS = Recommendations(
    items=[Recommendation(mal_id=1, title="Cowboy Bebop", summary="s", why_match="w")]
)


class StructuredChat:
    """Stands in for ChatGroq / ChatOpenAI / the venue's OpenAI-compatible client."""

    def __init__(self, *, fail: bool = False, parsed: Recommendations | None = RECS) -> None:
        self._fail = fail
        self._parsed = parsed

    def with_structured_output(self, schema, include_raw=False):  # type: ignore[no-untyped-def]
        def run(_):  # type: ignore[no-untyped-def]
            if self._fail:
                raise RuntimeError("provider exploded")
            return {"parsed": self._parsed, "raw": AIMessage(content="")}

        return RunnableLambda(run)


def _client(chat) -> _LangChainClient:  # type: ignore[no-untyped-def]
    return _LangChainClient(model_name="Qwen/Qwen2.5-7B-Instruct-AWQ", chat_model=chat)


@pytest.fixture
def durations(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(llm_mod, "record_llm_duration", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture
def ttfts(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(llm_mod, "record_llm_ttft", lambda **kw: calls.append(kw))
    return calls


@pytest.mark.asyncio
async def test_successful_call_records_duration_against_its_model(durations: list[dict]) -> None:
    result = await _client(StructuredChat()).recommend(query="q", context="c")

    assert result.items[0].title == "Cowboy Bebop"
    assert len(durations) == 1
    assert durations[0]["model"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"
    assert durations[0].get("outcome", "ok") == "ok"
    assert durations[0]["seconds"] >= 0


@pytest.mark.asyncio
async def test_failed_call_is_recorded_as_error_with_the_time_it_burned(
    durations: list[dict],
) -> None:
    """A provider that fails slowly is the expensive kind of failure — measure it."""
    with pytest.raises(RuntimeError, match="provider exploded"):
        await _client(StructuredChat(fail=True)).recommend(query="q", context="c")

    assert len(durations) == 1
    assert durations[0]["outcome"] == "error"
    assert durations[0]["seconds"] >= 0


@pytest.mark.asyncio
async def test_parse_failure_counts_as_an_error_not_a_success(durations: list[dict]) -> None:
    """A structured-output parse failure never reaches the success path."""
    with pytest.raises(RuntimeError, match="structured output parse failed"):
        await _client(StructuredChat(parsed=None)).recommend(query="q", context="c")

    assert [d["outcome"] for d in durations] == ["error"]


@pytest.mark.asyncio
async def test_streaming_records_ttft_once_on_the_first_token(ttfts: list[dict]) -> None:
    """TTFT is per stream, not per token: recording every token would flood it."""
    chat = RunnableLambda(lambda _: AIMessage(content="hello there"))
    tokens = [t async for t in _client(chat).astream(query="q", context="c")]

    assert "".join(tokens) == "hello there"
    assert len(ttfts) == 1
    assert ttfts[0]["model"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"
    assert ttfts[0]["seconds"] >= 0
