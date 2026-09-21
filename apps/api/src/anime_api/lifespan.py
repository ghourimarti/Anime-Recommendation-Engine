"""App lifespan — construct expensive singletons ONCE at startup.

The reranker model (~1.1 GB) and the LLM clients are app-level singletons stored
on `app.state`; the DB session is per-request (see dependencies.py). Constructing
the reranker per-request would reload the model on every call and destroy the TTFT
NFR — this separation is the single most performance-critical decision in the API.

Note: BgeReranker is lazy (weights download on first .score()), so startup stays
fast; the singleton still guarantees the model loads once, not per request.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anime_core.cache import get_cache
from anime_core.caches import EmbeddingCache, ResponseCache
from anime_core.cost_meter import CostMeter
from anime_core.db.engine import dispose_engine, session_scope
from anime_core.embedder import CachingEmbedder
from anime_core.embeddings import OpenAIEmbedder
from anime_core.killswitch import LlmKillSwitch
from anime_core.llm_client import build_default_llm_client
from anime_core.observability import get_langfuse_handler, loop_monitor, shutdown_langfuse
from anime_core.quotas import QuotaCounter
from anime_core.sqs import SqsJobPublisher
from anime_core.vector_index import PgvectorIndex
from anime_retrieval.catalog import load_catalog
from anime_retrieval.reranker import BgeReranker
from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: build singletons. Fail fast here if keys/config are missing.
    # One cache connection (NullCache if REDIS_URL unset — caching stays optional).
    cache = get_cache()
    app.state.cache = cache
    # The embedder is wrapped so query+corpus embeds share one embedding cache.
    app.state.embedder = CachingEmbedder(inner=OpenAIEmbedder(), cache=EmbeddingCache(cache))
    app.state.reranker = BgeReranker()
    # Warm the reranker: load the (baked-in) model into memory now so the FIRST
    # request doesn't pay the multi-second cold load and time out into hybrid
    # order. Runs in a thread (sync CPU work) but is awaited, so readiness only
    # flips green once the model is resident. Best-effort: if warm-up fails, log
    # and continue — the per-request path already degrades to hybrid gracefully.
    try:
        await asyncio.to_thread(app.state.reranker.warm)
    except Exception as exc:  # never let warm-up block startup
        logger.warning("reranker warm-up failed (%s); will lazy-load per request", exc)
    # The titles this deployment can talk about, read once. It answers "the user named
    # a show we do not have", which retrieval confidence provably cannot: the
    # absent-title query scores HIGHER than the median legitimate vague one, so a
    # threshold that caught it would refuse ~1 real query in 3 (measured 2026-09-20).
    # Loaded here, not per request, because it is a small lookup table that only
    # changes on re-ingest. load_catalog never raises: a failure yields an empty
    # catalogue, which fails OPEN.
    async with session_scope() as session:
        app.state.title_catalog = await load_catalog(session)
        # Warm the pgvector path in the same session we already opened. Dense retrieval
        # times out on the first ~2 requests after `make up` and then serves the same
        # query in 54ms, so the cost is first-use work landing on a real user -- who
        # silently gets sparse-only results, because retrieval degrades rather than
        # fails. Doing it here means readiness only goes green once the first query
        # would actually succeed, which is the same contract the reranker warm-up has.
        try:
            await PgvectorIndex(session).warm()
        except Exception as exc:  # advisory, exactly like the reranker warm-up
            logger.warning("dense warm-up failed (%s); first request may degrade", exc)
        else:
            logger.info("dense (pgvector) path warmed")
    # Langfuse callback wired into every LLM call so each Groq /
    # OpenAI invocation emits a trace with prompt / tokens / cost / latency.
    # Returns None when LANGFUSE_* env unset — the app boots without Langfuse.
    langfuse_handler = get_langfuse_handler()
    app.state.langfuse_handler = langfuse_handler
    callbacks = [langfuse_handler] if langfuse_handler is not None else None
    # build_default_llm_client wraps Tiered with the BudgetedLLMClient guard.
    app.state.llm = build_default_llm_client(callbacks=callbacks)
    app.state.response_cache = ResponseCache(cache)
    # Cost controls: per-user quota gate + cost meter. Both share the
    # cache handle; CostMeter is stateless (pure pricing math).
    app.state.quota_counter = QuotaCounter(cache)
    # The cost kill switch, readable at request time from Redis so it can be thrown
    # DURING an incident rather than after a redeploy. Falls back to LLM_ENABLED when
    # Redis cannot answer, which is what the switch did before it was flippable.
    app.state.kill_switch = LlmKillSwitch(cache)
    app.state.cost_meter = CostMeter()
    # SQS publisher for async jobs (feedback → eval, etc.).
    # Constructed once; publishing is fire-and-forget on the request path.
    app.state.job_publisher = SqsJobPublisher()
    # Event-loop lag sampler. The reference is held on app.state deliberately: a
    # bare create_task() can be garbage collected mid-flight, and the metric would
    # then stop with no error anywhere. Purely observational — it starts last so a
    # failure here can never prevent the app from serving.
    app.state.loop_monitor = loop_monitor.start()
    yield
    # Shutdown: stop the lag sampler first, so it cannot record against a loop that
    # is already tearing down.
    await loop_monitor.stop(getattr(app.state, "loop_monitor", None))
    # Shutdown: flush Langfuse so the in-flight traces actually land before the
    # process exits — without this, the last few traces silently drop in dev.
    shutdown_langfuse()
    # Shutdown: dispose the DB engine pool cleanly.
    await dispose_engine()
