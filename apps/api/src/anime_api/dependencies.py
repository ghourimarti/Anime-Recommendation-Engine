"""FastAPI dependency providers — bridge per-request and app-level lifetimes.

- get_session:    per-request async DB session (committed on response).
- get_repository: per-request data-access wrapper (shares the session).
- get_service:    per-request RecommendationService built from the per-request
                  session + the app-level singletons (embedder/reranker/llm).
- verify_db_ready: readiness probe — SELECT 1, raises 503 if the DB is unreachable.

FastAPI caches `get_session` within a request, so get_repository and get_service
share the same session instance.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from anime_core.db.engine import session_scope
from anime_retrieval.cached_service import CachedRecommendationService, Recommender
from anime_retrieval.pipeline import RetrievalPipeline
from anime_retrieval.service import RecommendationService
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from anime_api.repository import Repository


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


def get_repository(session: AsyncSession = Depends(get_session)) -> Repository:
    return Repository(session)


def get_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Recommender:
    state = request.app.state
    pipeline = RetrievalPipeline(
        session=session,
        embedder=state.embedder,
        reranker=state.reranker,
    )
    inner = RecommendationService(retriever=pipeline, llm=state.llm)
    # Response caching only, on a NORMALIZED query key. The semantic cache that used
    # to sit here was removed: measured on real query pairs, meaning-inverted
    # near-misses score higher on cosine than genuine paraphrases, so it could not
    # hit without sometimes answering the opposite question (see anime_core.caches).
    return CachedRecommendationService(
        inner=inner,
        response_cache=state.response_cache,
    )


async def verify_db_ready(session: AsyncSession = Depends(get_session)) -> None:
    """Readiness check: prove the DB is reachable, else 503."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database not ready",
        ) from exc
