"""Self-hosted venue client + confidence-based routing (D4b, S21).

TOPOLOGY
--------
    VenueRoutedClient
        ├── venue     = local vLLM/SGLang (OpenAI-compatible)  <- tried when confident
        └── hosted    = the existing TieredLLMClient           <- everything else

The venue WRAPS the tiered client rather than becoming a fourth tier inside it
(decision gate G1). Two reasons, and the second is the important one:

  1. TieredLLMClient carries hard-won measured history (Groq's 60% structured
     output failure rate, the SDK-retry latency disaster, the Groq-vs-OpenAI
     ordering reversal). Modifying it to add a tier risks all of that.

  2. When LLM_VENUE_ROUTING_ENABLED is false, VenueRoutedClient is never
     CONSTRUCTED - so "ships dark" is a structural guarantee, not a promise
     about a branch being taken. The flag-off code path is byte-identical to
     what ran before this module existed.

The venue is ADDITIVE, NEVER LOAD-BEARING. A home GPU is a single point of
failure on a residential uplink. Every venue failure path lands on the hosted
chain, which is exactly what serves 100% of traffic today - so the degraded
state IS the current production state.

WHY AN OpenAI CLIENT POINTS AT A LOCAL SERVER
---------------------------------------------
Both vLLM and SGLang expose an OpenAI-compatible /v1/chat/completions. So the
"adapter" is just ChatOpenAI with base_url overridden - no new client
hierarchy, no new dependency. That compatibility is the reason this step is
small; a bespoke protocol would have made it a subsystem.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any

from langchain_openai import ChatOpenAI

from anime_core.llm_client import LLMClient, _LangChainClient
from anime_core.observability.metrics import record_venue_decision
from anime_core.resilience import AsyncCircuitBreaker
from anime_core.schemas import Recommendations

logger = logging.getLogger(__name__)


# ─── The routing signal ───────────────────────────────────────────────────────
#
# The LLMClient protocol is recommend(*, query, context) - there is nowhere to
# pass a confidence score without changing every implementation. So we use the
# same vehicle the cost meter already uses for the mirror-image problem
# (carrying token usage OUT of the client): a ContextVar, task-scoped under
# asyncio, so concurrent requests never see each other's value.
#
# The retrieval service SETS this after reranking; the router READS it.
RETRIEVAL_CONFIDENCE: ContextVar[float | None] = ContextVar("retrieval_confidence", default=None)


def venue_enabled() -> bool:
    """The dark-ship gate. Default false - routing must be switched ON explicitly."""
    return os.environ.get("LLM_VENUE_ROUTING_ENABLED", "false").strip().lower() == "true"


def venue_url() -> str:
    return os.environ.get("LLM_VENUE_URL", "http://localhost:8001/v1")


def venue_model() -> str:
    return os.environ.get("LLM_VENUE_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")


def venue_timeout() -> float:
    return float(os.environ.get("VENUE_TIMEOUT", "20.0"))


def venue_confidence_threshold() -> float:
    """Route to the venue when top-1 rerank score >= this.

    MEASURED, NOT CHOSEN (S21.4a). `default_should_escalate` in llm_client.py
    warned that a confidence trigger is only legitimate "once we characterize
    the score distribution - we don't invent a threshold on a distribution we
    haven't measured." So 111 golden queries were run through the real
    pipeline and grouped by their own query_type label:

        type          n      p25   median      p75      max
        clear        55   -4.477   -0.486   +2.783   +7.563
        edge         28   -8.682   -3.219   -0.337   +5.575
        vague        18   -6.742   -4.843   -3.782   +0.519
        adversarial  10  -11.277  -11.254  -10.813   -9.701

    Monotonic in exactly the predicted order. Routing rates by threshold:

        T       clear    edge   vague  adversarial   overall
        0.0      47%     21%      6%        0%         30%
        1.0      44%     18%      0%        0%         26%     <- chosen
        2.0      35%     11%      0%        0%         20%

    1.0 is the LOWEST threshold at which no vague query reaches the small
    model, and it costs only 3 points of clear-query coverage versus 0.0. It
    is a boundary in the data, not a round number someone liked.

    Adversarial queries score 0% at every threshold down to -6.0 (their max is
    -9.70, below every other type's p25). Adversarial content structurally
    cannot reach the venue - that falls out of the measurement rather than
    needing a rule.

    TWO COUPLINGS THAT INVALIDATE THIS NUMBER:
      - The reranker model. These are raw cross-encoder logits from
        cross-encoder/ms-marco-MiniLM-L-12-v2. Change RERANKER_MODEL and the
        scale changes; re-run scripts/venue/measure_confidence.py.
      - The corpus. Measured on 269 titles. A materially different corpus
        shifts the distribution.

    Measured on curated golden queries, which are not real user traffic.
    Revisit against production once there is any.
    """
    return float(os.environ.get("VENUE_CONFIDENCE_THRESHOLD", "1.0"))


def should_use_venue(confidence: float | None) -> bool:
    """Venue only when retrieval was measurably confident.

    FAILS SAFE. `None` means no signal - retrieval returned nothing, or the
    reranker timed out and the pipeline degraded to hybrid order (which it
    does silently, at RERANK_TIMEOUT=2.0s, and does hit a cold cross-encoder).
    No signal means no confidence, which means the hosted chain. Treating a
    missing score as permission to use the cheap model would route exactly the
    queries we know least about to the weakest model.
    """
    if confidence is None:
        return False
    return confidence >= venue_confidence_threshold()


class VenueClient(_LangChainClient):
    """A self-hosted OpenAI-compatible endpoint (vLLM or SGLang).

    `api_key` is a required non-empty string for the OpenAI SDK even though the
    local server ignores it entirely - hence the placeholder rather than None,
    which raises.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        callbacks: list[Any] | None = None,
    ) -> None:
        resolved = model or venue_model()
        super().__init__(
            model_name=resolved,
            chat_model=ChatOpenAI(
                model=resolved,
                base_url=base_url or venue_url(),
                api_key=os.environ.get("LLM_VENUE_API_KEY", "not-needed"),  # type: ignore[arg-type]
                temperature=temperature,
                # Same reasoning as the hosted clients: fail fast, let the
                # fall-through to `hosted` be the retry strategy.
                max_retries=0,
            ),
            callbacks=callbacks,
            # Langfuse reads `langfuse_tags` off the invocation metadata. Traces are
            # already separable by model name; the tag makes "everything the venue
            # served" one filter regardless of which model is configured behind it.
            metadata={"langfuse_tags": ["venue", "self-hosted"]},
        )


class VenueRoutedClient:
    """Venue-first for confident queries; hosted chain for everything else.

    Failure handling is deliberately identical in shape to TieredLLMClient's
    fallback: catch, log, delegate. The user never learns the venue existed.

    But silent is not invisible. S19 found a 37x tail-latency problem hiding
    behind a working fallback, and llm_client's own docstring names the same
    trap ("a resilience mechanism doing its job so well that it hides the thing
    it is compensating for"). So every fall-through increments a counter that
    an operator can alert on - gate G4.
    """

    def __init__(self, *, venue: LLMClient, hosted: LLMClient) -> None:
        self._venue = venue
        self._hosted = hosted
        # Cheap in-process counters. Exported by observability.metrics; the
        # ratio fallbacks/attempts is the health signal that matters.
        self.venue_attempts = 0
        self.venue_fallbacks = 0

    @property
    def model(self) -> str:
        return f"venue-routed(venue={self._venue.model}, hosted={self._hosted.model})"

    def _route(self) -> tuple[LLMClient, bool]:
        confidence = RETRIEVAL_CONFIDENCE.get()
        if should_use_venue(confidence):
            return self._venue, True
        return self._hosted, False

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        client, is_venue = self._route()
        if not is_venue:
            record_venue_decision(decision="hosted")
            return await self._hosted.recommend(query=query, context=context)

        self.venue_attempts += 1
        try:
            result = await client.recommend(query=query, context=context)
        except Exception as exc:
            self.venue_fallbacks += 1
            record_venue_decision(decision="venue_fallback_error")
            logger.warning(
                "venue %s failed (%s); falling through to hosted %s",
                client.model,
                exc,
                self._hosted.model,
            )
            return await self._hosted.recommend(query=query, context=context)

        # A refusal from the venue is a real answer - never second-guess it.
        # Same reasoning as TieredLLMClient: re-asking a bigger model risks a
        # confabulation overruling a correct decline.
        if result.is_refusal:
            record_venue_decision(decision="venue_served")
            return result

        # Empty-without-refusal is the small-model whiff case. The 7B is the
        # weakest model in the chain, so this is the likeliest place to see it.
        if result.is_empty:
            self.venue_fallbacks += 1
            record_venue_decision(decision="venue_fallback_empty")
            logger.warning(
                "venue %s returned no recommendations; falling through to hosted %s",
                client.model,
                self._hosted.model,
            )
            hosted_result = await self._hosted.recommend(query=query, context=context)
            return hosted_result if not hosted_result.is_empty else result

        record_venue_decision(decision="venue_served")
        return result

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        client, is_venue = self._route()
        if not is_venue:
            record_venue_decision(decision="hosted")
            async for token in self._hosted.astream(query=query, context=context):
                yield token
            return

        self.venue_attempts += 1
        agen = client.astream(query=query, context=context)
        try:
            first = await agen.__anext__()
        except StopAsyncIteration:
            record_venue_decision(decision="venue_served")
            return
        except Exception as exc:
            # Only safe to fall through before the FIRST token - after that the
            # client has already received bytes and switching mid-stream would
            # splice two different models' prose together.
            self.venue_fallbacks += 1
            record_venue_decision(decision="venue_fallback_error")
            logger.warning(
                "venue %s stream failed (%s); falling through to hosted %s",
                client.model,
                exc,
                self._hosted.model,
            )
            async for token in self._hosted.astream(query=query, context=context):
                yield token
            return
        record_venue_decision(decision="venue_served")
        yield first
        async for token in agen:
            yield token


def build_venue_client(callbacks: list[Any] | None = None) -> LLMClient:
    """The venue leg: VenueClient behind the same breaker+timeout as every tier."""
    from anime_core.llm_client import ResilientLLMClient

    return ResilientLLMClient(
        inner=VenueClient(callbacks=callbacks),
        breaker=AsyncCircuitBreaker(name="venue"),
        timeout=venue_timeout(),
    )
