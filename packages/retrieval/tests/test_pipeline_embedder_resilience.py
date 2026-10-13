"""A failing query embedder must DEGRADE, never 500 (I.F13).

Measured 2026-09-22 by `make chain-drill` step 4: blackholing api.openai.com took out
the OpenAI LLM leg AND the text-embedding-3-small embedder. The embed call in
RetrievalPipeline.retrieve() was unguarded, so openai.APIConnectionError escaped
retrieval entirely — past the RetrievalUnavailableError handler in
RecommendationService.recommend(), and past the LLM degradation boundary below it,
which never even fired. Every request became HTTP 500 while the self-hosted LLM leg,
the Groq leg and the local Postgres corpus were all healthy.

The embedder is a remote call behind a cache, which is why this hid for so long: a
repeated query never reaches the provider, so only a cold cache key exposes it.

These tests pin the contract: embedder failure -> RetrievalUnavailableError, which the
service already translates into 200 + degraded + real corpus titles.
"""

from __future__ import annotations

import pytest
from anime_core.embeddings import EmbedResult
from anime_core.resilience import RetrievalUnavailableError
from anime_retrieval import pipeline as pipeline_module
from anime_retrieval.pipeline import RetrievalPipeline


class ProviderDown(RuntimeError):
    """Stands in for openai.APIConnectionError.

    Deliberately NOT the real class: the guard catches broadly on purpose, so the
    specific type is irrelevant to the contract, and coupling this test to the
    openai SDK's exception hierarchy would make it fragile for no gain.
    """


class FailingEmbedder:
    """Raises the way a provider outage does: on the call, not at construction."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    @property
    def model(self) -> str:
        return "failing"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise self._exc


class WorkingEmbedder:
    @property
    def model(self) -> str:
        return "working"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return EmbedResult(embeddings=[[1.0, 0.0]], total_tokens=0, latency_seconds=0.0)


class EmptySession:
    """The embedder fails before any statement runs, so this is never exercised."""

    async def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    async def rollback(self) -> None:
        return None


class NoReranker:
    def score(self, query, texts):  # type: ignore[no-untyped-def]
        return [0.0] * len(texts)


def _pipeline(embedder) -> RetrievalPipeline:  # type: ignore[no-untyped-def]
    return RetrievalPipeline(
        session=EmptySession(),  # type: ignore[arg-type]
        embedder=embedder,
        reranker=NoReranker(),
    )


@pytest.mark.asyncio
async def test_embedder_failure_raises_retrieval_unavailable() -> None:
    """The contract: the service's existing handler must be able to catch it.

    Before the fix this propagated the provider's own exception, which
    RecommendationService.recommend() does not catch -> HTTP 500.
    """
    embedder = FailingEmbedder(ProviderDown("All connection attempts failed"))

    with pytest.raises(RetrievalUnavailableError):
        await _pipeline(embedder).retrieve("a dark psychological thriller")

    assert embedder.calls == 1, "the embedder must actually have been called"


@pytest.mark.asyncio
async def test_original_exception_is_preserved_as_cause() -> None:
    """`raise ... from exc` — losing the cause would make a real outage undebuggable."""
    original = ProviderDown("All connection attempts failed")

    with pytest.raises(RetrievalUnavailableError) as caught:
        await _pipeline(FailingEmbedder(original)).retrieve("query")

    assert caught.value.__cause__ is original


@pytest.mark.asyncio
async def test_failed_embed_is_recorded_as_a_stage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An embedder burning its timeout on every request must not look FREE.

    Same reasoning the dense and sparse legs already apply in HybridRetriever.
    """
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        pipeline_module,
        "record_retrieval_stage",
        lambda **kw: seen.append(kw),
    )

    with pytest.raises(RetrievalUnavailableError):
        await _pipeline(FailingEmbedder(ProviderDown("down"))).retrieve("query")

    embed_stages = [s for s in seen if s.get("stage") == "embed"]
    assert len(embed_stages) == 1, "the failed embed must be recorded exactly once"
    assert embed_stages[0]["outcome"] == "error"
    assert isinstance(embed_stages[0]["seconds"], float)


@pytest.mark.asyncio
async def test_timeout_is_recorded_as_timeout_not_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A slow provider and a refusing one are different incidents; keep them apart."""
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        pipeline_module,
        "record_retrieval_stage",
        lambda **kw: seen.append(kw),
    )

    with pytest.raises(RetrievalUnavailableError):
        await _pipeline(FailingEmbedder(TimeoutError())).retrieve("query")

    embed_stages = [s for s in seen if s.get("stage") == "embed"]
    assert embed_stages[0]["outcome"] == "timeout"


@pytest.mark.asyncio
async def test_negative_control_working_embedder_does_not_raise(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """NEGATIVE CONTROL. Without this the tests above could pass for the wrong reason.

    If `retrieve` raised RetrievalUnavailableError unconditionally — or if this fake
    pipeline could never reach the embed call — every assertion above would still be
    green while proving nothing. This proves the guard is selective, and that a
    healthy embed records outcome-free (i.e. successful).
    """
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        pipeline_module,
        "record_retrieval_stage",
        lambda **kw: seen.append(kw),
    )

    # No candidates come back (EmptySession returns no rows), which is a legitimate
    # empty result and NOT an availability failure.
    result = await _pipeline(WorkingEmbedder()).retrieve("query")

    assert result == []
    embed_stages = [s for s in seen if s.get("stage") == "embed"]
    assert len(embed_stages) == 1
    assert "outcome" not in embed_stages[0], "a successful embed must not be flagged"
