"""housekeeping.popular_precompute handler.

Computes a fresh "popular this week" set and writes it to Redis. This is the
fresher floor beneath anime_core.fallback's STATIC popular list: when the LLM
tier + retrieval are both down, the degraded response can serve THIS instead of
a hard-coded list.

Source of truth: thumbs-up feedback over the trailing 7 days, top-N by count.
Clean SQL aggregation (vs parsing query_history JSON). If feedback is sparse the
set is just smaller — callers still fall back to the static list when it's empty.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from anime_core.db.models import Feedback
from sqlalchemy import func, select

from anime_worker.handlers.base import HandlerContext

logger = logging.getLogger(__name__)

POPULAR_KEY = "popular:this_week"
POPULAR_TTL_SECONDS = 8 * 24 * 3600  # 8 days — outlives the 7-day window + a recompute miss
TOP_N = 10


async def handle_popular_precompute(payload: dict[str, Any], ctx: HandlerContext) -> None:
    window_days = int(payload.get("window_days", 7))
    since = datetime.now(UTC) - timedelta(days=window_days)

    async with ctx.session_factory() as session:
        stmt = (
            select(Feedback.mal_id, func.count().label("up"))
            .where(Feedback.rating == 1, Feedback.created_at >= since)
            .group_by(Feedback.mal_id)
            .order_by(func.count().desc())
            .limit(TOP_N)
        )
        rows = (await session.execute(stmt)).all()

    mal_ids = [int(r.mal_id) for r in rows]
    await ctx.cache.set(POPULAR_KEY, json.dumps(mal_ids), ttl_seconds=POPULAR_TTL_SECONDS)
    logger.info("popular_precompute wrote %d mal_ids to %s", len(mal_ids), POPULAR_KEY)
