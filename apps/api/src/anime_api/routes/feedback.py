"""Feedback endpoint — captures thumbs up/down per recommendation.

Feeds the online-eval + future-personalization loop. Scoped to
the authenticated user. After persisting, it enqueues a
feedback.recorded job — fire-and-forget: a queue outage logs and degrades, it
NEVER fails the user's feedback POST.
"""

from __future__ import annotations

import logging

from anime_core.jobs import JobMessage, JobPublisher, JobType
from fastapi import APIRouter, Depends

from anime_api.auth import AuthedUser, get_current_user
from anime_api.dependencies import get_repository
from anime_api.quota import get_job_publisher
from anime_api.repository import Repository
from anime_api.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: AuthedUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
    publisher: JobPublisher | None = Depends(get_job_publisher),
) -> FeedbackResponse:
    await repo.ensure_user(user_id=user.id, email=user.email)
    feedback_id = await repo.add_feedback(
        user_id=user.id,
        query_history_id=body.query_history_id,
        mal_id=body.mal_id,
        rating=body.rating,
    )

    # Enqueue async eval processing — fire-and-forget. The idempotency_key is the
    # feedback row id, so a duplicate publish (e.g. a client retry) dedups in the
    # worker. A publish failure must NOT fail the user's request.
    if publisher is not None:
        try:
            await publisher.publish(
                JobMessage(
                    type=JobType.FEEDBACK_RECORDED,
                    idempotency_key=f"feedback:{feedback_id}",
                    payload={
                        "feedback_id": feedback_id,
                        "query_history_id": body.query_history_id,
                        "mal_id": body.mal_id,
                        "rating": body.rating,
                    },
                )
            )
        except Exception:
            logger.warning("failed to enqueue feedback.recorded job; continuing", exc_info=True)

    return FeedbackResponse(id=feedback_id)
