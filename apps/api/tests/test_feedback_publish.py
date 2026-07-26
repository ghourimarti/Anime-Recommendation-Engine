"""the feedback route enqueues a job, and a publish failure is non-fatal."""

from __future__ import annotations

from typing import Any

import pytest
from anime_api.quota import get_job_publisher
from anime_core.jobs import InMemoryJobPublisher, JobType


@pytest.mark.asyncio
async def test_feedback_publishes_job(app: Any, client: Any) -> None:
    pub = InMemoryJobPublisher()
    app.dependency_overrides[get_job_publisher] = lambda: pub

    resp = await client.post("/v1/feedback", json={"mal_id": 19, "rating": -1})
    assert resp.status_code == 200

    assert len(pub.published) == 1
    msg = pub.published[0]
    assert msg.type is JobType.FEEDBACK_RECORDED
    assert msg.payload["mal_id"] == 19
    assert msg.payload["rating"] == -1
    # Idempotency key is the feedback row id (FakeRepository returns 7).
    assert msg.idempotency_key == "feedback:7"


@pytest.mark.asyncio
async def test_publish_failure_does_not_fail_request(app: Any, client: Any) -> None:
    """A queue outage must not break the user's feedback POST."""

    class BoomPublisher:
        async def publish(self, message: Any) -> None:
            raise RuntimeError("sqs down")

    app.dependency_overrides[get_job_publisher] = lambda: BoomPublisher()

    resp = await client.post("/v1/feedback", json={"mal_id": 1, "rating": 1})
    assert resp.status_code == 200  # still recorded; publish failure swallowed


@pytest.mark.asyncio
async def test_no_publisher_is_fine(app: Any, client: Any) -> None:
    """When no publisher is wired (publisher=None), feedback still works."""
    app.dependency_overrides[get_job_publisher] = lambda: None
    resp = await client.post("/v1/feedback", json={"mal_id": 1, "rating": 1})
    assert resp.status_code == 200
