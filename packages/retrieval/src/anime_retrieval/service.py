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
from anime_core.llm_client import LLMClient
from anime_core.observability.metrics import record_refusal, record_retrieval_confidence
from anime_core.resilience import RetrievalUnavailableError
from anime_core.schemas import RecommendationResult, Recommendations
from anime_core.venue import RETRIEVAL_CONFIDENCE

from anime_retrieval.types import Candidate

logger = logging.getLogger(__name__)

# Per-candidate text cap fed to the LLM. The retrieved set is already top-3/5, so a
# simple char cap is sufficient context control at this scale (full token-budget
# accounting is overkill until the corpus/candidate count grows).
MAX_CANDIDATE_CHARS = 800


def _llm_enabled() -> bool:
    """Cost kill switch: LLM_ENABLED=false short-circuits generation."""
    return os.environ.get("LLM_ENABLED", "true").strip().lower() != "false"


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

    def __init__(self, *, retriever: Retriever, llm: LLMClient) -> None:
        self._retriever = retriever
        self._llm = llm

    async def recommend(self, query: str, *, tenant_id: str | None = None) -> RecommendationResult:
        # Cost kill switch: skip the LLM entirely, serve the popular floor.
        if not _llm_enabled():
            return popular_fallback(DEGRADED_NOTICE)

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
        RETRIEVAL_CONFIDENCE.set(_top_rerank_confidence(candidates))

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
        if not _llm_enabled():
            yield DEGRADED_NOTICE
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
        RETRIEVAL_CONFIDENCE.set(_top_rerank_confidence(candidates))
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
