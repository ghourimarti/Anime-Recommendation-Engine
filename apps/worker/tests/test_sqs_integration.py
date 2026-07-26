"""Opt-in LocalStack integration test for the real SQS round-trip.

Excluded from `make test` (marked `integration`); run with LocalStack up:

    docker compose up -d localstack
    AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test \
      AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
      uv run pytest -m integration apps/worker/tests/test_sqs_integration.py

Proves the parts the unit tests fake: queue + DLQ creation with a real redrive
policy, publish via SqsJobPublisher, and receive via the aiobotocore client.
"""

from __future__ import annotations

import json
import uuid

import pytest
from anime_core.jobs import JobMessage, JobType, QueueCategory
from anime_core.sqs import _client_kwargs, ensure_queues, queue_name

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_ensure_queues_creates_main_and_dlq_with_redrive() -> None:
    from aiobotocore.session import get_session

    await ensure_queues([QueueCategory.FEEDBACK])
    sess = get_session()
    async with sess.create_client("sqs", **_client_kwargs()) as sqs:
        url = (await sqs.get_queue_url(QueueName=queue_name(QueueCategory.FEEDBACK)))["QueueUrl"]
        attrs = await sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["RedrivePolicy"])
        policy = json.loads(attrs["Attributes"]["RedrivePolicy"])
        assert policy["maxReceiveCount"] == 5
        assert policy["deadLetterTargetArn"].endswith("-dlq")


@pytest.mark.asyncio
async def test_publish_then_receive_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    import anime_core.sqs as sqs_mod
    from aiobotocore.session import get_session
    from anime_core.sqs import SqsJobPublisher

    # Own an isolated queue: a live worker (docker compose) long-polls the default
    # anime-dev-feedback queue and would race us for the message. A unique prefix
    # routes ensure_queues/publish/receive onto a queue no worker consumes.
    monkeypatch.setattr(sqs_mod, "QUEUE_PREFIX", f"anime-test-{uuid.uuid4().hex[:8]}")

    await ensure_queues([QueueCategory.FEEDBACK])
    msg = JobMessage(
        type=JobType.FEEDBACK_RECORDED,
        idempotency_key="feedback:integration-1",
        payload={"mal_id": 1, "rating": 1},
    )
    await SqsJobPublisher().publish(msg)

    sess = get_session()
    async with sess.create_client("sqs", **_client_kwargs()) as sqs:
        url = (await sqs.get_queue_url(QueueName=queue_name(QueueCategory.FEEDBACK)))["QueueUrl"]
        resp = await sqs.receive_message(QueueUrl=url, WaitTimeSeconds=5, MaxNumberOfMessages=1)
        bodies = [m["Body"] for m in resp.get("Messages", [])]
        assert any("feedback:integration-1" in b for b in bodies)
