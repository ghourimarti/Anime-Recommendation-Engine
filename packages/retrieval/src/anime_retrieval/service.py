"""RecommendationService — the retrieve → generate orchestrator.

Combines the retrieval pipeline (Steps 2-4) with the LLM client:

    query → retrieve candidates → build context → LLM → GROUND output → Recommendations

Grounding: the LLM is asked to copy mal_ids from the candidates,
but LLMs hallucinate IDs. We validate every returned mal_id against the actual
retrieved set and drop any that don't match — output validation at the boundary,
not blind trust. This lives in retrieval (not core) because it depends on both
the retrieval Candidate type and the core LLM client.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Protocol

from anime_core.fallback import DEGRADED_NOTICE, NO_MATCH_NOTICE, popular_fallback
from anime_core.killswitch import LlmKillSwitch, llm_enabled_from_env
from anime_core.llm_client import LLMClient
from anime_core.observability.metrics import record_refusal, record_retrieval_confidence
from anime_core.resilience import RetrievalUnavailableError
from anime_core.schemas import RecommendationResult, Recommendations
from anime_core.venue import RETRIEVAL_CONFIDENCE

from anime_retrieval.catalog import TitleCatalog, refusal_for
from anime_retrieval.types import Candidate

logger = logging.getLogger(__name__)

# Per-candidate text cap fed to the LLM. The retrieved set is already top-3/5, so a
# simple char cap is sufficient context control at this scale (full token-budget
# accounting is overkill until the corpus/candidate count grows).
MAX_CANDIDATE_CHARS = 800

# Refuse WITHOUT calling the LLM when retrieval found nothing that resembles the
# query. A raw cross-encoder logit, the same quantity _top_rerank_confidence()
# returns, so the number is comparable to VENUE_CONFIDENCE_THRESHOLD (which is 1.0
# in this space) -- but it answers a different question and is nowhere near it.
#
# CALIBRATED, not chosen (2026-09-20, 10 adversarial + 59 answerable golden queries,
# retrieval only, no LLM):
#
#     threshold   refusal_recall   false_refusal_rate
#      -11.00         0.70               0.00
#      -10.75         0.80               0.00
#       -9.50         1.00               0.10
#       -7.00         1.00               0.25
#
# -11.0 buys the deterministic half of the win with the largest margin to the
# nearest legitimate query (-10.72, from the HARD_ANSWERABLE over-refusal set):
# 0.28 logit. -10.75 scores better on paper and leaves 0.03, which is not a margin,
# it is a coincidence. Recall below 1.00 is fine here because this is a FLOOR, not
# the refusal policy: the LLM still declines what it declines today.
#
# WHAT THIS DOES NOT DO: it does not fix the named-but-absent-title case (I.F6).
# "tell me about Demon Slayer and Jujutsu Kaisen" scores -4.339 -- HIGHER than the
# median legitimate vague query (-4.843) -- because the corpus is full of similar
# shounen and the reranker correctly finds them. Catching that class needs a
# threshold that refuses ~1 in 3 real queries. Confidence answers "is anything here
# similar", never "does the title you named exist". That needs a title lookup.
REFUSE_BELOW_CONFIDENCE = float(os.environ.get("REFUSE_BELOW_CONFIDENCE", "-11.0"))

# Deliberately not the NO_MATCH_NOTICE popular fallback: that hands back three
# popular anime, which for an out-of-scope question is the confabulation this gate
# exists to stop. An honest empty answer is the product.
OUT_OF_SCOPE_REFUSAL = (
    "I only cover anime in this catalogue, and nothing in it matches that. "
    "Try describing the kind of show you want -- a genre, a mood, or a premise."
)


def _llm_enabled() -> bool:
    """Cost kill switch, environment half: LLM_ENABLED=false short-circuits generation.

    Kept as the fallback rather than replaced. When no LlmKillSwitch is injected (tests,
    the eval harness) or Redis cannot answer, this is the answer -- which is exactly what
    the code did before the switch became flippable at runtime.
    """
    return llm_enabled_from_env()


def _top_rerank_confidence(candidates: list[Candidate]) -> float | None:
    """Retrieval confidence for venue routing (D4b): the first non-None rerank score.

    THIS DEFINITION IS LOAD-BEARING. The routing threshold (1.0) was derived by
    scripts/venue/measure_confidence.py, which took exactly this quantity — the
    first candidate in the returned order that carries a rerank score. Computing
    anything else here (max score, mean of top-3, post-MMR position) would
    silently invalidate the threshold, because it would be a different
    distribution from the one that was measured.

    Returns None when the reranker did not run. That is a real and routine case,
    not a defensive nicety: RERANK_TIMEOUT is 2.0s and the cross-encoder lazily
    loads its weights, so the pipeline degrades to hybrid order (rerank_score
    None on every candidate) after a cold start. should_use_venue() treats None
    as "no confidence" and routes to the hosted chain.
    """
    for candidate in candidates:
        if candidate.rerank_score is not None:
            # Recorded here rather than at the call sites so both recommend() and
            # astream() are covered by construction. Only emitted when a score
            # exists - a reranker timeout has nothing meaningful to record, and a
            # sentinel would corrupt the distribution we compare against.
            record_retrieval_confidence(candidate.rerank_score)
            return candidate.rerank_score
    return None


class Retriever(Protocol):
    """Anything that turns a query into ranked Candidates (the real pipeline or a fake)."""

    async def retrieve(self, query: str, *, tenant_id: str | None = None) -> list[Candidate]: ...


def build_context(candidates: list[Candidate]) -> str:
    """Format candidates into the CANDIDATES block, each tagged with its mal_id."""
    parts = [f"[mal_id={c.mal_id}]\n{c.text[:MAX_CANDIDATE_CHARS]}" for c in candidates]
    return "\n\n".join(parts)


def _candidate_title(text: str) -> str:
    """Extract the 'Title: ...' header the chunker wrote onto every candidate."""
    first_line = text.split("\n", 1)[0]
    if first_line.startswith("Title: "):
        return first_line[len("Title: ") :].strip()
    return ""


def ground_recommendations(recs: Recommendations, candidates: list[Candidate]) -> Recommendations:
    """Force every recommendation onto a real retrieved anime.

    Two-stage grounding, because small models botch the mal_id even when they
    pick the right anime:
      1. If the returned mal_id is in the retrieved set → keep as-is.
      2. Else, match the returned title to a candidate's title (case-insensitive,
         substring either direction) and CANONICALIZE the mal_id to the real one.
      3. Else, drop it (a genuine hallucination).

    Stage 2 is what saves us when the LLM gets the recommendation right but the
    ID wrong — far better than dropping a correct recommendation over a typo'd ID.
    """
    valid_ids = {c.mal_id for c in candidates}
    title_to_id: dict[str, int] = {
        _candidate_title(c.text).lower(): c.mal_id for c in candidates if _candidate_title(c.text)
    }

    grounded = []
    for r in recs.items:
        if r.mal_id in valid_ids:
            grounded.append(r)
            continue
        canonical = _match_title(r.title, title_to_id)
        if canonical is not None:
            grounded.append(r.model_copy(update={"mal_id": canonical}))
        # else: genuine hallucination → drop
    return Recommendations(items=grounded)


def _match_title(title: str, title_to_id: dict[str, int]) -> int | None:
    """Match a returned title to a candidate title; return its mal_id or None."""
    needle = title.strip().lower()
    if not needle:
        return None
    if needle in title_to_id:
        return title_to_id[needle]
    for cand_title, mal_id in title_to_id.items():
        if needle in cand_title or cand_title in needle:
            return mal_id
    return None


class RecommendationService:
    """Orchestrates retrieval + generation + grounding."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        llm: LLMClient,
        catalog: TitleCatalog | None = None,
        kill_switch: LlmKillSwitch | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        # Optional like `catalog`: without one the switch is env-only, which is the
        # behaviour every caller had before it could be flipped at runtime.
        self._kill_switch = kill_switch
        # Optional so every existing construction (tests, eval harness) keeps working
        # and simply skips the check, which is the pre-existing behaviour.
        self._catalog = catalog

    async def _generation_enabled(self) -> bool:
        """Redis first, environment second. See anime_core.killswitch for why."""
        if self._kill_switch is not None:
            return await self._kill_switch.llm_enabled()
        return _llm_enabled()

    def _named_but_absent(self, query: str) -> list[str]:
        """Titles the query names that this catalogue does not have."""
        return self._catalog.missing_titles(query) if self._catalog else []

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        # Cost kill switch: skip the LLM entirely, serve the popular floor.
        if not await self._generation_enabled():
            return popular_fallback(DEGRADED_NOTICE)

        # The user named a show and we do not have it. Answer that BEFORE retrieval:
        # it does not depend on what retrieval finds, and the alternative is what this
        # system used to do -- hand back three unrelated titles as though they were the
        # answer. Retrieval confidence cannot make this call (measured: the absent-title
        # query scores HIGHER than the median legitimate vague one), which is why this
        # is a lookup rather than a threshold. See anime_retrieval.catalog.
        if missing := self._named_but_absent(query):
            logger.info("query names titles not in the catalogue: %s", missing)
            record_refusal()
            return RecommendationResult(items=[], refusal=refusal_for(missing))

        # Retrieval — pgvector→FTS fallback lives in the pipeline; if BOTH fail it
        # raises RetrievalUnavailableError → we degrade to popular.
        try:
            candidates = await self._retriever.retrieve(query, tenant_id=tenant_id)
        except RetrievalUnavailableError:
            logger.warning("retrieval unavailable; serving popular fallback")
            return popular_fallback(DEGRADED_NOTICE)

        if not candidates:
            return popular_fallback(NO_MATCH_NOTICE)

        # Publish retrieval confidence for venue routing (D4b). Set unconditionally,
        # even when routing is disabled: the LLMClient protocol is
        # recommend(*, query, context), so there is no parameter to pass this
        # through, and a ContextVar is the same vehicle the cost meter already uses
        # for the mirror-image problem. Task-scoped under asyncio, so concurrent
        # requests never read each other's value. Nothing consumes it while the
        # flag is off.
        confidence = _top_rerank_confidence(candidates)
        RETRIEVAL_CONFIDENCE.set(confidence)

        # The deterministic floor, BEFORE any LLM call. Two reasons it is here and
        # not in the prompt: the answer is then identical whichever tier serves
        # (measured 2026-09-20: Groq refused 9/9 where the gpt-4o-mini fallback
        # answered 3/3 on the same query), and an out-of-scope question stops
        # costing a generation at all.
        #
        # `confidence is None` means the reranker did not run, NOT that the match is
        # poor -- a RERANK_TIMEOUT or a cold start produces exactly that. Refusing on
        # it would turn a slow host into a refusal storm, so this fails OPEN and the
        # LLM decides, as it does today.
        if confidence is not None and confidence < REFUSE_BELOW_CONFIDENCE:
            logger.info("retrieval confidence %.3f below floor; refusing", confidence)
            record_refusal()
            return RecommendationResult(items=[], refusal=OUT_OF_SCOPE_REFUSAL)

        context = build_context(candidates)

        # Generation — TieredLLMClient handles Groq→OpenAI internally; if every tier
        # fails it raises, and we degrade rather than 500.
        try:
            recs = await self._llm.recommend(query=query, context=context)
        except Exception:  # the LLM degradation boundary — any failure → popular
            logger.warning("all LLM tiers failed; serving popular fallback", exc_info=True)
            return popular_fallback(DEGRADED_NOTICE)

        # The model declined — honour it. This check MUST come before grounding.
        #
        # A refusal is an empty answer, and the grounding branch below turns an empty
        # answer into the popular fallback. So without this, a model that correctly
        # refused "how do I file my taxes" would have its refusal quietly overwritten
        # with three popular anime — the same confabulation, arriving through a
        # different door. The system would look like it was answering the question.
        #
        # This is NOT degraded: the system is perfectly healthy and the honest answer
        # is "nothing". Marking it degraded would page someone and would (correctly)
        # bypass the cache, so we'd re-pay for the LLM to decline the same nonsense
        # query every time.
        if recs.is_refusal:
            logger.info("model refused the request: %s", recs.refusal)
            record_refusal()
            return RecommendationResult(items=[], refusal=recs.refusal)

        grounded = ground_recommendations(recs, candidates)
        if grounded.is_empty:
            # The model returned items and NONE survived grounding — it named anime
            # that were not in the candidate set. That is a quality failure, not a
            # refusal, and the popular floor is the designed degradation for it.
            return popular_fallback(NO_MATCH_NOTICE)
        return RecommendationResult.of(grounded)

    async def astream(self, query: str, *, tenant_id: str | None = None) -> AsyncIterator[str]:
        if not await self._generation_enabled():
            yield DEGRADED_NOTICE
            return
        # Same check as recommend(), for the same reason: both entry points must
        # refuse the same things.
        if missing := self._named_but_absent(query):
            logger.info("query names titles not in the catalogue: %s", missing)
            record_refusal()
            yield refusal_for(missing)
            return
        try:
            candidates = await self._retriever.retrieve(query, tenant_id=tenant_id)
        except RetrievalUnavailableError:
            yield DEGRADED_NOTICE
            return
        if not candidates:
            yield NO_MATCH_NOTICE
            return
        # Same confidence publication as recommend() — both entry points must set
        # it, or streaming requests would route on whatever value a previous
        # request happened to leave in the ContextVar's default.
        confidence = _top_rerank_confidence(candidates)
        RETRIEVAL_CONFIDENCE.set(confidence)
        # Same floor as recommend(), or the two entry points would disagree about
        # what the product refuses -- and the streaming one would be the lenient one.
        if confidence is not None and confidence < REFUSE_BELOW_CONFIDENCE:
            logger.info("retrieval confidence %.3f below floor; refusing", confidence)
            record_refusal()
            yield OUT_OF_SCOPE_REFUSAL
            return
        context = build_context(candidates)
        # Graceful degradation on the streaming path — mirror the
        # structured recommend() guard. Without this, an LLM failure on BOTH
        # tiers propagates out of the StreamingResponse and the client sees a
        # raw "Failed to fetch" instead of a friendly notice. TieredLLMClient
        # falls back BEFORE the first token, so a total outage raises here before
        # anything is yielded → we emit the degraded notice cleanly.
        try:
            async for token in self._llm.astream(query=query, context=context):
                yield token
        except Exception:
            logger.warning("streaming LLM failed; emitting degraded notice", exc_info=True)
            yield DEGRADED_NOTICE
