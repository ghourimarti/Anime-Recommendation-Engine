"""Unit tests for the job contract."""

from __future__ import annotations

import pytest
from anime_core.jobs import (
    InMemoryJobPublisher,
    JobMessage,
    JobType,
    QueueCategory,
)


def test_job_routes_to_correct_queue() -> None:
    assert JobMessage(type=JobType.FEEDBACK_RECORDED).queue is QueueCategory.FEEDBACK
    assert JobMessage(type=JobType.REEMBED_CORPUS).queue is QueueCategory.INGESTION
    assert JobMessage(type=JobType.POPULAR_PRECOMPUTE).queue is QueueCategory.HOUSEKEEPING
    assert JobMessage(type=JobType.GDPR_DELETE).queue is QueueCategory.HOUSEKEEPING


def test_idempotency_key_defaults_to_id_when_unset() -> None:
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED)
    assert msg.idempotency_key == msg.id


def test_explicit_idempotency_key_is_preserved() -> None:
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED, idempotency_key="feedback:42")
    assert msg.idempotency_key == "feedback:42"


def test_serialize_roundtrip() -> None:
    msg = JobMessage(
        type=JobType.GDPR_DELETE,
        payload={"user_id": "u1"},
        idempotency_key="gdpr:u1",
    )
    raw = msg.model_dump_json()
    back = JobMessage.model_validate_json(raw)
    assert back.type is JobType.GDPR_DELETE
    assert back.payload == {"user_id": "u1"}
    assert back.idempotency_key == "gdpr:u1"


@pytest.mark.asyncio
async def test_in_memory_publisher_records() -> None:
    pub = InMemoryJobPublisher()
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED, idempotency_key="feedback:1")
    await pub.publish(msg)
    assert len(pub.published) == 1
    assert pub.published[0].idempotency_key == "feedback:1"
