"""Async job contract — shared by the API (producer) and the
worker (consumer).

A `JobMessage` is the wire format on every queue. The two load-bearing fields:
  - `type`            routes the message to a handler in the worker.
  - `idempotency_key` lets the consumer dedup at-least-once redeliveries. It MUST
    be set deterministically by the PRODUCER (e.g. f"feedback:{feedback_id}") so a
    duplicate publish carries the SAME key and is recognised as a repeat.

`JobType` → queue-category mapping lives here so producer and consumer agree on
which queue a job lands in (one queue per worker category).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class JobType(StrEnum):
    """Every async job kind. The value is the on-the-wire `type` discriminator."""

    FEEDBACK_RECORDED = "feedback.recorded"
    REEMBED_CORPUS = "reembed.corpus"
    POPULAR_PRECOMPUTE = "housekeeping.popular_precompute"
    GDPR_DELETE = "gdpr.delete_user"


class QueueCategory(StrEnum):
    """The three worker queues. Each scales independently in KEDA."""

    FEEDBACK = "feedback"
    INGESTION = "ingestion"
    HOUSEKEEPING = "housekeeping"


# Which queue each job type is published to / consumed from.
JOB_QUEUE: dict[JobType, QueueCategory] = {
    JobType.FEEDBACK_RECORDED: QueueCategory.FEEDBACK,
    JobType.REEMBED_CORPUS: QueueCategory.INGESTION,
    JobType.POPULAR_PRECOMPUTE: QueueCategory.HOUSEKEEPING,
    JobType.GDPR_DELETE: QueueCategory.HOUSEKEEPING,
}


class JobMessage(BaseModel):
    """The wire format for every async job."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    # Deterministic per logical event — set by the producer, used by the consumer
    # to dedup redeliveries. Defaults to the message id (no dedup) if a producer
    # genuinely has no natural key, but real producers SHOULD set it.
    idempotency_key: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_post_init(self, _ctx: object) -> None:
        if not self.idempotency_key:
            object.__setattr__(self, "idempotency_key", self.id)

    @property
    def queue(self) -> QueueCategory:
        return JOB_QUEUE[self.type]


class JobPublisher(Protocol):
    """Anything that can enqueue a JobMessage. Implemented by SqsJobPublisher
    (prod) and InMemoryJobPublisher (tests)."""

    async def publish(self, message: JobMessage) -> None: ...


class InMemoryJobPublisher:
    """Test double — records published messages instead of hitting SQS."""

    def __init__(self) -> None:
        self.published: list[JobMessage] = []

    async def publish(self, message: JobMessage) -> None:
        self.published.append(message)
