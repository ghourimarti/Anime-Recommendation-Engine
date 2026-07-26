"""Tests for the tiered LLM client — escalation + fallback routing, no network."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.llm_client import TieredLLMClient, default_should_escalate
from anime_core.schemas import Recommendation, Recommendations


class SpyClient:
    """Records calls; optionally raises to simulate an outage."""

    def __init__(self, name: str, *, fail: bool = False, tokens: list[str] | None = None) -> None:
        self._name = name
        self._fail = fail
        self._tokens = tokens or [name]
        self.recommend_calls = 0
        self.stream_calls = 0

    @property
    def model(self) -> str:
        return self._name

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self.recommend_calls += 1
        if self._fail:
            raise RuntimeError(f"{self._name} down")
        return Recommendations(
            items=[Recommendation(mal_id=1, title=self._name, summary="s", why_match="w")]
        )

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        self.stream_calls += 1
        if self._fail:
            raise RuntimeError(f"{self._name} down")
        for t in self._tokens:
            yield t


def _tiered(default: SpyClient, escalation: SpyClient, fallback: SpyClient) -> TieredLLMClient:
    return TieredLLMClient(default=default, escalation=escalation, fallback=fallback)


def test_default_should_escalate_threshold() -> None:
    assert default_should_escalate("short query") is False
    long_query = " ".join(["word"] * 30)
    assert default_should_escalate(long_query) is True


@pytest.mark.asyncio
async def test_short_query_uses_default() -> None:
    d, e, f = SpyClient("default"), SpyClient("esc"), SpyClient("fallback")
    result = await _tiered(d, e, f).recommend(query="short", context="ctx")
    assert result.items[0].title == "default"
    assert d.recommend_calls == 1 and e.recommend_calls == 0 and f.recommend_calls == 0


@pytest.mark.asyncio
async def test_long_query_escalates() -> None:
    d, e, f = SpyClient("default"), SpyClient("esc"), SpyClient("fallback")
    long_query = " ".join(["complex"] * 30)
    result = await _tiered(d, e, f).recommend(query=long_query, context="ctx")
    assert result.items[0].title == "esc"
    assert e.recommend_calls == 1 and d.recommend_calls == 0


@pytest.mark.asyncio
async def test_fallback_on_primary_failure() -> None:
    d, e, f = SpyClient("default", fail=True), SpyClient("esc"), SpyClient("fallback")
    result = await _tiered(d, e, f).recommend(query="short", context="ctx")
    assert result.items[0].title == "fallback"
    assert d.recommend_calls == 1 and f.recommend_calls == 1


class EmptyClient:
    """Returns valid-but-empty recommendations (a small-model soft failure)."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.recommend_calls = 0

    @property
    def model(self) -> str:
        return self._name

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self.recommend_calls += 1
        return Recommendations(items=[])

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        yield self._name


@pytest.mark.asyncio
async def test_empty_primary_triggers_fallback() -> None:
    # primary "succeeds" but returns no items → fallback should be tried
    d = EmptyClient("default")
    e = SpyClient("esc")
    f = SpyClient("fallback")
    result = await _tiered(d, e, f).recommend(query="short", context="ctx")
    assert result.items[0].title == "fallback"
    assert d.recommend_calls == 1 and f.recommend_calls == 1


@pytest.mark.asyncio
async def test_stream_uses_default_then_falls_back() -> None:
    d = SpyClient("default", tokens=["a", "b", "c"])
    e, f = SpyClient("esc"), SpyClient("fallback", tokens=["x", "y"])
    out = [t async for t in _tiered(d, e, f).astream(query="short", context="ctx")]
    assert out == ["a", "b", "c"]

    d_fail = SpyClient("default", fail=True)
    out2 = [t async for t in _tiered(d_fail, e, f).astream(query="short", context="ctx")]
    assert out2 == ["x", "y"]  # fell back before first token


# ── config must be read lazily, not at import time ────────────────────────────


def test_model_config_is_read_lazily_not_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE regression test for the import-order config trap.

    These settings used to be module-level constants (`X = os.environ.get(...)`),
    frozen the instant anime_core.llm_client was imported. Containers got away with
    it — docker sets the environment before Python starts. Every local entrypoint did
    not: its import graph pulls anime_core in long before its own load_dotenv() line
    runs, so the constants froze to their DEFAULTS.

    The result was silent and total: local scripts ran llama-3.1-8b-instant instead of
    the configured openai/gpt-oss-20b, with a 600-token input budget instead of 3000.
    llama-3.1-8b does not honour the structured-output schema, so it returned zero
    recommendations and fell through to the fallback on every single call. Local eval
    was measuring a different model from production and nothing said a word.

    Config read at import time makes correctness depend on import ORDER, which nobody
    reviews. So: read it when it's used.
    """
    from anime_core.llm_client import (
        default_groq_model,
        escalation_groq_model,
        fallback_openai_model,
        llm_max_input_tokens,
        llm_max_output_tokens,
    )

    # Simulate a load_dotenv() that lands AFTER this module was imported.
    monkeypatch.setenv("GROQ_DEFAULT_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_ESCALATION_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_MAX_INPUT_TOKENS", "3000")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "1500")

    assert default_groq_model() == "openai/gpt-oss-20b"
    assert escalation_groq_model() == "llama-3.3-70b-versatile"
    assert fallback_openai_model() == "gpt-4o"
    assert llm_max_input_tokens() == 3000
    assert llm_max_output_tokens() == 1500


def test_config_falls_back_to_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from anime_core.llm_client import default_groq_model, llm_max_input_tokens

    monkeypatch.delenv("GROQ_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LLM_MAX_INPUT_TOKENS", raising=False)
    assert default_groq_model() == "llama-3.1-8b-instant"
    assert llm_max_input_tokens() == 600
