"""LLM client layer (two-tier Groq + OpenAI fallback) behind one
interface, using LangChain v1.

Topology:
    default     = Groq llama-3.1-8b-instant     (fast, cheap — most queries)
    escalation  = Groq llama-3.3-70b-versatile  (harder/complex queries)
    fallback    = OpenAI gpt-4o-mini             (Groq outage)

`TieredLLMClient` composes the three. Escalation (quality routing) is a
difficulty heuristic; fallback (availability routing) is try/except. Full
circuit-breaker resilience is layered on top; here we establish the structure.

Structured output uses `llm.with_structured_output(Recommendations)` (LangChain's
documented idiom for typed output); streaming uses a plain LCEL chain.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol, cast

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from anime_core.cost_meter import LAST_USAGE, TokenUsage
from anime_core.prompts import RECOMMEND_PROMPT, STREAM_PROMPT
from anime_core.resilience import AsyncCircuitBreaker, BudgetExceededError, guarded
from anime_core.schemas import Recommendations

logger = logging.getLogger(__name__)


# ─── Config is read LAZILY, never at import time ──────────────────────────────
#
# These used to be module-level constants (`X = os.environ.get(...)`), evaluated the
# moment anime_core.llm_client was imported. In the containers that happens to work,
# because docker populates the environment before Python starts.
#
# Everywhere else it silently broke. A local script's import graph pulls in
# anime_core long before its `load_dotenv()` line runs — so the constants froze to
# their DEFAULTS, and every local entrypoint quietly ran:
#     model = llama-3.1-8b-instant   (not the configured openai/gpt-oss-20b)
#     LLM_MAX_INPUT_TOKENS = 600     (not the configured 3000)
# which is doubly unlucky, because .env.example itself notes that llama-3.1-8b does
# NOT honour the structured-output schema — it invents field names, returns zero
# recommendations, and falls through to the fallback every single time.
#
# So local eval and every local script were exercising a completely different model
# and a 5x smaller token budget than production, and nothing said so. Config read at
# import time is a trap: it makes correctness depend on import ORDER, which nobody
# reviews.
def default_groq_model() -> str:
    return os.environ.get("GROQ_DEFAULT_MODEL", "llama-3.1-8b-instant")


def escalation_groq_model() -> str:
    return os.environ.get("GROQ_ESCALATION_MODEL", "llama-3.3-70b-versatile")


def fallback_openai_model() -> str:
    return os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")


def groq_timeout() -> float:
    return float(os.environ.get("GROQ_TIMEOUT", "10.0"))


def openai_timeout() -> float:
    return float(os.environ.get("OPENAI_TIMEOUT", "15.0"))


def llm_max_input_tokens() -> int:
    return int(os.environ.get("LLM_MAX_INPUT_TOKENS", "600"))


def llm_max_output_tokens() -> int:
    return int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "1200"))


def llm_sdk_max_retries() -> int:
    """Retries INSIDE the provider SDK. Default 0 — and that 0 is load-bearing.

    LangChain's ChatGroq/ChatOpenAI default to max_retries=2 with exponential backoff.
    Nobody set it, so nobody saw it. But we already HAVE a retry strategy — the tiered
    fallback (Groq default → Groq escalation → OpenAI) wrapped in circuit breakers — and
    stacking the SDK's retries underneath it means a failing primary retries twice with
    backoff BEFORE our fallback is even allowed to run.

    Measured, and it is not subtle. 12 real requests: p50 2.86s (fine), p95 19.90s,
    max 24.76s — against an 8s p95 NFR. The logs show exactly where it goes:

        primary LLM openai/gpt-oss-20b raised (400 Tool call validation failed)
        Retrying request to /openai/v1/chat/completions in 3.000000 seconds
        Retrying request to /openai/v1/chat/completions in 11.000000 seconds
        ... falling back to gpt-4o-mini

    24.76s ≈ GROQ_TIMEOUT (10s, spent on SDK backoff) + OPENAI_TIMEOUT (15s). The user
    waited 25 seconds for an answer the fallback could have produced in three.

    Retrying is also just wrong for this failure. A 400 "tool call validation failed" is
    deterministic: the same prompt to the same model returns the same 400. Backing off
    and asking again, twice, is a slower way to fail. And when it IS a 429, the fallback
    to a DIFFERENT provider is a far better response than politely waiting for the one
    that is rate-limiting us.

    So: fail fast at the SDK, and let the fallback chain — which is the strategy we
    actually designed — do the work.
    """
    return int(os.environ.get("LLM_SDK_MAX_RETRIES", "0"))


def default_should_escalate(query: str) -> bool:
    """Escalate long/complex queries to the bigger model.

    Word count is a deterministic, testable proxy for complexity. A
    confidence-based trigger (retrieval rerank score) is a v2 refinement once we
    characterize the score distribution — we don't invent a threshold on a
    distribution we haven't measured.
    """
    threshold = int(os.environ.get("ESCALATION_WORD_THRESHOLD", "25"))
    return len(query.split()) > threshold


class LLMClient(Protocol):
    """A single model endpoint: structured recommend + token stream."""

    @property
    def model(self) -> str: ...

    async def recommend(self, *, query: str, context: str) -> Recommendations: ...

    def astream(self, *, query: str, context: str) -> AsyncIterator[str]: ...


class _LangChainClient:
    """Shared LangChain-backed implementation; subclasses supply the chat model.

    `callbacks` is the per-client list of LangChain Callbacks (e.g. Langfuse's
    CallbackHandler). Passed at INVOCATION via
    config={"callbacks": ...} so a future per-request callback list (e.g. for
    per-tenant trace destinations) is a clean refactor. None disables callbacks.
    """

    def __init__(
        self,
        *,
        model_name: str,
        chat_model: ChatGroq | ChatOpenAI,
        callbacks: list[Any] | None = None,
    ) -> None:
        self._model_name = model_name
        self._chat = chat_model
        self._callbacks = callbacks

    @property
    def model(self) -> str:
        return self._model_name

    def _invoke_config(self) -> RunnableConfig | None:
        if not self._callbacks:
            return None
        return RunnableConfig(callbacks=self._callbacks)

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        # `include_raw=True` surfaces both the parsed structured output AND the
        # underlying AIMessage with usage_metadata. We need the latter to record
        # per-tenant cost without weaving callbacks through every
        # layer. Documented LangChain v1 idiom; both ChatGroq and ChatOpenAI
        # support it.
        chain = RECOMMEND_PROMPT | self._chat.with_structured_output(
            Recommendations, include_raw=True
        )
        # include_raw=True returns dict[{"raw", "parsed", "parsing_error"}]; the
        # cast tells mypy we know this. LangChain types it polymorphically because
        # the same call shape supports include_raw=False (returns the model).
        result = cast(
            dict[str, Any],
            await chain.ainvoke({"query": query, "context": context}, config=self._invoke_config()),
        )
        parsed = result.get("parsed")
        if parsed is None:
            # Surface the structured-output parsing error rather than masking it
            # behind an empty Recommendations — TieredLLMClient's empty-result
            # logic would then misclassify a parser bug as a "small model whiff".
            error = result.get("parsing_error") or RuntimeError(
                "structured output parse failed without an error"
            )
            raise error
        # Emit usage to the cost-meter ContextVar so the route can record cost
        # after the call. ContextVar is task-scoped (asyncio) — concurrent
        # requests never see each other's usage.
        raw = result.get("raw")
        usage_meta = getattr(raw, "usage_metadata", None) or {}
        LAST_USAGE.set(
            TokenUsage(
                model=self._model_name,
                input_tokens=int(usage_meta.get("input_tokens", 0)),
                output_tokens=int(usage_meta.get("output_tokens", 0)),
            )
        )
        return cast(Recommendations, parsed)

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        chain = STREAM_PROMPT | self._chat | StrOutputParser()
        async for token in chain.astream(
            {"query": query, "context": context}, config=self._invoke_config()
        ):
            yield token


class GroqClient(_LangChainClient):
    """Groq-hosted model (default + escalation tiers)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        callbacks: list[Any] | None = None,
    ) -> None:
        # Resolve at CONSTRUCTION, not import: by now any entrypoint's load_dotenv()
        # has run, so we get the configured model rather than the compiled-in default.
        resolved = model or default_groq_model()
        super().__init__(
            model_name=resolved,
            chat_model=ChatGroq(
                model=resolved,
                temperature=temperature,
                # 0: fail fast and let the TIERED FALLBACK handle it — see llm_sdk_max_retries.
                max_retries=llm_sdk_max_retries(),
            ),
            callbacks=callbacks,
        )


class OpenAIClient(_LangChainClient):
    """OpenAI fallback (gpt-4o-mini)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        callbacks: list[Any] | None = None,
    ) -> None:
        resolved = model or fallback_openai_model()
        super().__init__(
            model_name=resolved,
            chat_model=ChatOpenAI(
                model=resolved,
                temperature=temperature,
                max_retries=llm_sdk_max_retries(),
            ),
            callbacks=callbacks,
        )


class TieredLLMClient:
    """Composes default/escalation/fallback into one LLMClient."""

    def __init__(
        self,
        *,
        default: LLMClient,
        escalation: LLMClient,
        fallback: LLMClient,
        should_escalate: Callable[[str], bool] | None = None,
    ) -> None:
        self._default = default
        self._escalation = escalation
        self._fallback = fallback
        self._should_escalate = should_escalate or default_should_escalate

    @property
    def model(self) -> str:
        return f"tiered(default={self._default.model}, fallback={self._fallback.model})"

    def _primary(self, query: str) -> LLMClient:
        return self._escalation if self._should_escalate(query) else self._default

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        primary = self._primary(query)
        try:
            result = await primary.recommend(query=query, context=context)
        except Exception as exc:
            logger.warning(
                "primary LLM %s raised (%s); falling back to %s",
                primary.model,
                exc,
                self._fallback.model,
            )
            return await self._fallback.recommend(query=query, context=context)

        # A REFUSAL is a deliberate, correct answer — never retry it.
        #
        # Empty-but-refusing and empty-because-broken look identical if you only check
        # is_empty, and the branch below treats "empty" as a soft failure worth burning
        # a fallback call on. So a model that correctly declined "how do I file my
        # taxes" would be second-guessed by a bigger, pricier model, asked the same
        # nonsense question — and if THAT one confabulated three anime, the
        # confabulation would win. We would have paid extra to overrule the right
        # answer.
        if result.is_refusal:
            return result

        # An EMPTY structured result with no refusal IS a soft failure — small models
        # often emit a valid-but-empty tool call. Retry on the fallback before giving up.
        if result.is_empty and primary is not self._fallback:
            logger.warning(
                "primary LLM %s returned no recommendations; trying fallback %s",
                primary.model,
                self._fallback.model,
            )
            fallback_result = await self._fallback.recommend(query=query, context=context)
            return fallback_result if not fallback_result.is_empty else result
        return result

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        primary = self._primary(query)
        agen = primary.astream(query=query, context=context)
        try:
            first = await agen.__anext__()
        except StopAsyncIteration:
            return
        except Exception as exc:
            logger.warning(
                "primary LLM %s stream failed (%s); falling back to %s",
                primary.model,
                exc,
                self._fallback.model,
            )
            async for token in self._fallback.astream(query=query, context=context):
                yield token
            return
        yield first
        async for token in agen:
            yield token


class ResilientLLMClient:
    """Wraps a single LLMClient with a circuit breaker + timeout.

    The structured `recommend` path is breaker+timeout guarded: a flapping or slow
    provider trips its breaker and fast-fails, so TieredLLMClient drops to the next
    tier immediately instead of waiting out repeated timeouts. `astream` delegates
    (per-token streaming timeouts are awkward; the tiered fallback covers it).
    """

    def __init__(self, *, inner: LLMClient, breaker: AsyncCircuitBreaker, timeout: float) -> None:
        self._inner = inner
        self._breaker = breaker
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._inner.model

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        return await guarded(
            lambda: self._inner.recommend(query=query, context=context),
            breaker=self._breaker,
            timeout_seconds=self._timeout,
        )

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        async for token in self._inner.astream(query=query, context=context):
            yield token


class BudgetedLLMClient:
    """Per-request input-token budget guard.

    Wraps an LLMClient and refuses oversized inputs BEFORE the provider is called.
    Sits at the TOP of the composition (above TieredLLMClient): the budget is a
    per-request hard cap, not per-tier — refusing should NOT cause a tier fallback,
    so it lives outside Tiered/Resilient.

    Why word-count x 1.5 instead of tiktoken (Decision G4 in the build walkthrough):
      - tiktoken adds a dep, is slow on the hot path, and is wrong for Llama anyway.
      - 1.5x is conservative (over-estimates English tokens), so the cap is safe.
      - Precision belongs in the meter, where we use real usage_metadata for free.

    `max_output_tokens` is recorded but not enforced here — the LLM stops on its
    own; higher layers may pass it as a generation hint. We keep it on the
    client so the route layer doesn't have to thread budget knobs separately.
    """

    def __init__(
        self,
        *,
        inner: LLMClient,
        max_input_tokens: int,
        max_output_tokens: int,
    ) -> None:
        self._inner = inner
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    @property
    def max_output_tokens(self) -> int:
        return self._max_output_tokens

    def _estimated_input_tokens(self, query: str, context: str) -> int:
        # 1.5 tokens per word (English) is conservative for both BPE and
        # SentencePiece tokenizers used by Llama / GPT.
        words = len(query.split()) + len(context.split())
        return int(words * 1.5)

    def _check_budget(self, query: str, context: str) -> None:
        estimated = self._estimated_input_tokens(query, context)
        if estimated > self._max_input_tokens:
            raise BudgetExceededError(
                f"input ~{estimated} tokens exceeds budget {self._max_input_tokens}"
            )

    async def recommend(self, *, query: str, context: str) -> Recommendations:
        self._check_budget(query, context)
        return await self._inner.recommend(query=query, context=context)

    async def astream(self, *, query: str, context: str) -> AsyncIterator[str]:
        self._check_budget(query, context)
        async for token in self._inner.astream(query=query, context=context):
            yield token


def llm_primary_provider() -> str:
    """Which provider serves the FIRST attempt: "openai" (default) or "groq".

    ─── Provider order, revised on measurement (2026-07-14) ──────────────────────
    The first cut put Groq first for time-to-first-token. That was the right instinct and the
    wrong conclusion, because it assumed Groq could produce our structured output.
    Measured against the real Recommendations schema, on 10 real queries each:

        model                       structured-output failures
        openai/gpt-oss-20b                  60%
        openai/gpt-oss-120b                 50%
        llama-3.3-70b-versatile             30%
        moonshotai/kimi-k2-instruct        100%

    Every Groq model fails, at a similar rate, with the same error:

        Tool call validation failed: attempted to call tool 'recommendations'
        which was not in request.tools

    The model emits the tool name lower-cased and Groq's validator is case-sensitive.
    It is a provider-side tool-calling quirk, not a model-quality problem — which is
    exactly why swapping Groq models doesn't help. (Registering the tool under a
    lower-case name, and json_mode/json_schema, were both tried and are worse.)

    The system still returned correct answers throughout, because the OpenAI fallback
    silently carried it. That is the failure mode worth naming: a resilience mechanism
    doing its job so well that it hides the thing it is compensating for. What it cost:

        ~50% of requests made TWO LLM calls
        p95 8.81s against an 8s NFR
        double the token spend on every fallback

    A "fast" primary that fails half the time and forces a second call is slower and
    dearer than one reliable call. So the reliable provider goes first, and Groq stays
    in the chain as the availability fallback — the tiering is intact, the ORDER is now
    driven by measured reliability rather than by advertised speed.

    ─── AND THEN THE MEASUREMENT SAID OTHERWISE ─────────────────────────────────
    Reliability-first was tried and it is WORSE. Measured, 12 uncached requests each:

        config                     p50      p95     fallbacks
        Groq first (no SDK retry)  2.67s    8.81s   5/12
        OpenAI first               7.18s   10.57s   0/12

    OpenAI never falls back — and is slow every single time (~7s/call from this region).
    Groq's SUCCESS path is ~1s. So Groq-first trades "always slow" for "usually fast,
    sometimes slow", and usually-fast wins on both p50 and p95.

    So the default stays GROQ, on evidence rather than on the original speed assumption.
    The knob exists because the evidence could change: if Groq fixes its tool-call
    validation the fallback rate collapses and this gets strictly better, and if OpenAI
    ever becomes the faster leg, LLM_PRIMARY=openai is one restart away. The eval and
    refusal gates are what tell you whether a flip is safe.

    KNOWN GAP: p95 8.81s against an 8s NFR. The p95 request is one that fell back, and
    the OpenAI leg alone is ~7s from this region. The NFR is met on the primary path
    (2.67s) and missed on the fallback path — so it closes when Groq's structured-output
    failure rate drops, not by tuning timeouts. Documented rather than papered over.
    """
    return os.environ.get("LLM_PRIMARY", "groq").strip().lower()


def build_default_tiered_client(
    callbacks: list[Any] | None = None,
) -> TieredLLMClient:
    """Construct the production tier from env-configured models.

    Each provider is wrapped with its own breaker + timeout so a failing tier
    fast-fails and the next tier takes over.

    `callbacks`: LangChain Callbacks (e.g. Langfuse handler)
    threaded into every tier so EVERY actual LLM call gets traced, regardless of
    which tier serves the response.
    """
    groq_default = ResilientLLMClient(
        inner=GroqClient(model=default_groq_model(), callbacks=callbacks),
        breaker=AsyncCircuitBreaker(name="groq-default"),
        timeout=groq_timeout(),
    )
    groq_escalation = ResilientLLMClient(
        inner=GroqClient(model=escalation_groq_model(), callbacks=callbacks),
        breaker=AsyncCircuitBreaker(name="groq-escalation"),
        timeout=groq_timeout(),
    )
    openai_client = ResilientLLMClient(
        inner=OpenAIClient(model=fallback_openai_model(), callbacks=callbacks),
        breaker=AsyncCircuitBreaker(name="openai"),
        timeout=openai_timeout(),
    )

    if llm_primary_provider() == "groq":
        # The original Groq-first order. Kept switchable, not deleted: it becomes correct again
        # the moment Groq's tool-call validation stops rejecting the model's own output.
        return TieredLLMClient(
            default=groq_default, escalation=groq_escalation, fallback=openai_client
        )

    # Reliability-first (default): OpenAI serves, Groq is the availability fallback.
    return TieredLLMClient(default=openai_client, escalation=openai_client, fallback=groq_default)


def build_default_llm_client(
    callbacks: list[Any] | None = None,
) -> BudgetedLLMClient:
    """The production composition: Budget → Tiered → Resilient → Provider.

    Budget sits at the TOP so an oversized request refuses *once*, not once per
    tier. Tiered sits next so cost/availability routing happens before the
    breakers. Resilient (breaker + timeout) sits closest to the network call.

    `callbacks` are threaded down to each provider client so
    every LLM call emits its Langfuse trace regardless of tier selection.

    This is what `lifespan.py` wires onto `app.state.llm`.
    """
    return BudgetedLLMClient(
        inner=build_default_tiered_client(callbacks=callbacks),
        max_input_tokens=llm_max_input_tokens(),
        max_output_tokens=llm_max_output_tokens(),
    )
