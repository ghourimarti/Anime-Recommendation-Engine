"""Tests for self-hosted venue routing (D4b, S21) — no network, no GPU.

The two tests that actually protect production are the ones nobody writes:
`test_flag_off_composition_is_unchanged` (the dark-ship guarantee) and the
fall-through family (the venue is additive, never load-bearing). The happy path
is the least interesting thing here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from anime_core.schemas import Recommendation, Recommendations
from anime_core.venue import (
    RETRIEVAL_CONFIDENCE,
    VenueRoutedClient,
    should_use_venue,
    venue_confidence_threshold,
    venue_enabled,
)


class SpyClient:
    """Records calls; can simulate an outage, an empty answer, or a refusal."""

    def __init__(self, name: str, *, behaviour: str = "ok") -> None:
        self._name = name
        self._behaviour = behaviour
        self.recommend_calls = 0
        self.stream_calls = 0

    @property
    def model(self) -> str:
        return self._name

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self.recommend_calls += 1
        if self._behaviour == "raise":
            raise RuntimeError(f"{self._name} down")
        if self._behaviour == "empty":
            return Recommendations(items=[])
        if self._behaviour == "refuse":
            return Recommendations(items=[], refusal="out of scope")
        return Recommendations(
            items=[Recommendation(mal_id=1, title=self._name, summary="s", why_match="w")]
        )

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        self.stream_calls += 1
        if self._behaviour == "raise":
            raise RuntimeError(f"{self._name} down")
        yield self._name


def _routed(venue: SpyClient, hosted: SpyClient) -> VenueRoutedClient:
    return VenueRoutedClient(venue=venue, hosted=hosted)


@pytest.fixture(autouse=True)
def _clear_confidence():
    """Each test sets its own confidence; never inherit another test's value."""
    token = RETRIEVAL_CONFIDENCE.set(None)
    yield
    RETRIEVAL_CONFIDENCE.reset(token)


# ── the routing decision ──────────────────────────────────────────────────────


def test_threshold_default_is_the_measured_value():
    """1.0 was derived from the golden-set score distribution, not chosen.

    If this changes, scripts/venue/measure_confidence.py must be re-run — the
    number is only defensible as the output of that measurement.
    """
    assert venue_confidence_threshold() == 1.0


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (5.0, True),
        (1.0, True),  # boundary is inclusive
        (0.99, False),
        (-9.0, False),
        (None, False),
    ],
)
def test_should_use_venue(confidence, expected):
    assert should_use_venue(confidence) is expected


def test_missing_confidence_fails_safe_to_hosted():
    """None is the reranker-timed-out case, and it is routine, not theoretical.

    RERANK_TIMEOUT is 2.0s against a lazily-loaded cross-encoder, so a cold
    start yields no score at all. Treating "no signal" as permission to use the
    cheapest model would send precisely the queries we know least about to the
    weakest model in the chain.
    """
    assert should_use_venue(None) is False


def test_venue_disabled_by_default(monkeypatch):
    """The dark-ship gate. Absent config must not enable routing."""
    monkeypatch.delenv("LLM_VENUE_ROUTING_ENABLED", raising=False)
    assert venue_enabled() is False


# ── the fall-through contract: the venue is additive, never load-bearing ──────


@pytest.mark.anyio
async def test_below_threshold_never_touches_the_venue():
    venue, hosted = SpyClient("venue"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(-5.0)

    result = await client.recommend(query="q", context="c")

    assert venue.recommend_calls == 0
    assert hosted.recommend_calls == 1
    assert result.items[0].title == "hosted"


@pytest.mark.anyio
async def test_above_threshold_is_served_by_the_venue():
    venue, hosted = SpyClient("venue"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(2.5)

    result = await client.recommend(query="q", context="c")

    assert venue.recommend_calls == 1
    assert hosted.recommend_calls == 0
    assert result.items[0].title == "venue"
    assert client.venue_attempts == 1
    assert client.venue_fallbacks == 0


@pytest.mark.anyio
async def test_venue_failure_falls_through_and_user_still_gets_an_answer():
    venue, hosted = SpyClient("venue", behaviour="raise"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(2.5)

    result = await client.recommend(query="q", context="c")

    assert venue.recommend_calls == 1
    assert hosted.recommend_calls == 1
    assert result.items[0].title == "hosted"  # the user never learns the venue existed
    assert client.venue_fallbacks == 1


@pytest.mark.anyio
async def test_venue_empty_result_falls_through():
    """Empty-without-refusal is the small-model whiff; the 7B is the likeliest source."""
    venue, hosted = SpyClient("venue", behaviour="empty"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(2.5)

    result = await client.recommend(query="q", context="c")

    assert hosted.recommend_calls == 1
    assert result.items[0].title == "hosted"
    assert client.venue_fallbacks == 1


@pytest.mark.anyio
async def test_venue_refusal_is_honoured_not_second_guessed():
    """A refusal is a correct answer. Re-asking a bigger model risks a
    confabulation overruling it — the same reasoning TieredLLMClient applies."""
    venue, hosted = SpyClient("venue", behaviour="refuse"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(2.5)

    result = await client.recommend(query="q", context="c")

    assert result.refusal == "out of scope"
    assert hosted.recommend_calls == 0, "a refusal must not trigger a fall-through"


# ── streaming ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_stream_below_threshold_uses_hosted():
    venue, hosted = SpyClient("venue"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(-5.0)

    tokens = [t async for t in client.astream(query="q", context="c")]

    assert tokens == ["hosted"]
    assert venue.stream_calls == 0


@pytest.mark.anyio
async def test_stream_venue_failure_falls_through_before_first_token():
    """Fall-through is only safe BEFORE the first token — after that the client
    has already received bytes, and switching would splice two models' prose."""
    venue, hosted = SpyClient("venue", behaviour="raise"), SpyClient("hosted")
    client = _routed(venue, hosted)
    RETRIEVAL_CONFIDENCE.set(2.5)

    tokens = [t async for t in client.astream(query="q", context="c")]

    assert tokens == ["hosted"]
    assert client.venue_fallbacks == 1


# ── composition: the dark-ship guarantee ──────────────────────────────────────


def test_flag_off_composition_is_unchanged(monkeypatch):
    """THE test that makes "ships dark" a guarantee rather than a promise.

    With the flag off, VenueRoutedClient must never be constructed — so the
    object graph is the one that existed before venue.py was written, not a
    branch we believe is equivalent to it.
    """
    from anime_core.llm_client import TieredLLMClient, build_default_llm_client

    monkeypatch.setenv("LLM_VENUE_ROUTING_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    client = build_default_llm_client()

    assert isinstance(client._inner, TieredLLMClient)


def test_flag_on_wraps_the_untouched_tiered_client(monkeypatch):
    """Routing is ADDITIVE: the hosted leg must still be the tiered client,
    unmodified, so the degraded path is exactly today's production path."""
    from anime_core.llm_client import TieredLLMClient, build_default_llm_client

    monkeypatch.setenv("LLM_VENUE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    client = build_default_llm_client()

    assert isinstance(client._inner, VenueRoutedClient)
    assert isinstance(client._inner._hosted, TieredLLMClient)


# ── cost attribution ──────────────────────────────────────────────────────────


def test_venue_model_is_priced_at_zero_without_explicit_config(monkeypatch):
    """Self-hosted tokens have no marginal cost, and that must not depend on
    somebody remembering to edit LLM_PRICING — otherwise flipping the flag
    kills the first venue request with UnknownModelError, on the hot path."""
    from anime_core.cost_meter import CostMeter, get_pricing

    monkeypatch.setenv("LLM_VENUE_MODEL", "some/local-model")
    monkeypatch.setenv("LLM_PRICING", '{"gpt-4o-mini":["0.15","0.60"]}')
    get_pricing.cache_clear()

    meter = CostMeter()
    assert meter.cost_for(model="some/local-model", input_tokens=1000, output_tokens=500) == 0
    get_pricing.cache_clear()


def test_explicit_pricing_overrides_the_zero_default(monkeypatch):
    """Config beats default — the zero rate is a fallback, not a policy."""
    from anime_core.cost_meter import CostMeter, get_pricing

    monkeypatch.setenv("LLM_VENUE_MODEL", "some/local-model")
    monkeypatch.setenv("LLM_PRICING", '{"some/local-model":["1.00","2.00"]}')
    get_pricing.cache_clear()

    meter = CostMeter()
    assert meter.cost_for(model="some/local-model", input_tokens=1_000_000, output_tokens=0) == 1
    get_pricing.cache_clear()
