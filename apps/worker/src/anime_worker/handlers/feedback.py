"""feedback.recorded handler — seed the online-eval loop.

When a user thumbs a recommendation, the API enqueues a feedback.recorded job.
Here we turn it into eval signal:
  - bump a rolling feedback counter (observability / sampling rate base),
  - for THUMBS-DOWN, push (query_history_id, mal_id) onto a capped review queue
    so the eval pipeline can later sample disliked recs for a
    groundedness/quality review.

Cache-only — no DB. Idempotency is handled by the consumer; this handler is
naturally safe to run twice (counter over-count by one is immaterial; the review
queue is a bounded set we sample, not a ledger).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anime_worker.handlers.base import HandlerContext

logger = logging.getLogger(__name__)

FEEDBACK_COUNT_KEY = "eval:feedback_count"
REVIEW_QUEUE_KEY = "eval:review_queue"
REVIEW_QUEUE_MAX = 500


async def handle_feedback_recorded(payload: dict[str, Any], ctx: HandlerContext) -> None:
    rating = int(payload.get("rating", 0))
    await ctx.cache.incr(FEEDBACK_COUNT_KEY)
    if rating < 0:
        member = json.dumps(
            {
                "query_history_id": payload.get("query_history_id"),
                "mal_id": payload.get("mal_id"),
            }
        )
        await ctx.cache.push_capped(REVIEW_QUEUE_KEY, member, max_len=REVIEW_QUEUE_MAX)
        logger.info("queued thumbs-down for eval review: mal_id=%s", payload.get("mal_id"))
