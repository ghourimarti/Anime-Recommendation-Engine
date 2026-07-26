"""gdpr.delete_user handler — GDPR right-to-be-forgotten.

Hard-deletes every row carrying a user's PII. Order matters: child rows first,
the users row last.

The CRITICAL detail: query_history.user_id and feedback.user_id are
ON DELETE SET NULL — so deleting the users row alone would ORPHAN the PII
(the query text + thumbs stay, just unlinked). For GDPR we must DELETE those
rows, not null their FK. So we explicitly delete each child table by user_id.

Idempotent: deleting an already-deleted user affects 0 rows. Safe to retry.
"""

from __future__ import annotations

import logging
from typing import Any

from anime_core.db.models import Feedback, QueryHistory, UsageDaily, User
from sqlalchemy import delete

from anime_worker.handlers.base import HandlerContext

logger = logging.getLogger(__name__)


async def handle_gdpr_delete(payload: dict[str, Any], ctx: HandlerContext) -> None:
    user_id = payload.get("user_id")
    if not user_id:
        raise ValueError("gdpr.delete_user requires a 'user_id' in the payload")

    async with ctx.session_factory() as session:
        # Children first (explicit delete — NOT relying on SET NULL, which would
        # orphan PII rather than remove it).
        await session.execute(delete(Feedback).where(Feedback.user_id == user_id))
        await session.execute(delete(QueryHistory).where(QueryHistory.user_id == user_id))
        await session.execute(delete(UsageDaily).where(UsageDaily.user_id == user_id))
        # Then the identity row itself.
        await session.execute(delete(User).where(User.id == user_id))

    logger.info("gdpr.delete_user completed for user_id=%s", user_id)
