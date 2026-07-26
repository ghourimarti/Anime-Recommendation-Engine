"""SQS transport — async publisher + queue bootstrap.

aiobotocore gives an asyncio-native SQS client (boto3 is sync and would block the
event loop in the FastAPI producer). One `aiobotocore.Session` is created per
publisher/consumer; each call opens a short-lived client from it.

Queue resolution: queue NAMES are derived from QueueCategory + an env prefix
(so dev/staging/prod don't collide on one AWS account). The endpoint + creds come
from env — `AWS_ENDPOINT_URL` points at LocalStack in dev, unset in real AWS.

`ensure_queues` creates each main queue + its `<name>-dlq` with a RedrivePolicy
(maxReceiveCount) so poison messages land in the DLQ instead of looping forever.
It's idempotent (CreateQueue is a no-op if the queue exists with the same attrs).
"""

from __future__ import annotations

import json
import logging
import os

from aiobotocore.session import AioSession, get_session

from anime_core.jobs import JobMessage, QueueCategory

logger = logging.getLogger(__name__)

# Prefix isolates environments on a shared AWS account (anime-dev-feedback, ...).
QUEUE_PREFIX = os.environ.get("SQS_QUEUE_PREFIX", "anime-dev")
# After this many failed receives, SQS moves the message to the DLQ (Decision G3).
MAX_RECEIVE_COUNT = int(os.environ.get("SQS_MAX_RECEIVE_COUNT", "5"))


def queue_name(category: QueueCategory) -> str:
    return f"{QUEUE_PREFIX}-{category.value}"


def dlq_name(category: QueueCategory) -> str:
    return f"{queue_name(category)}-dlq"


def _client_kwargs() -> dict[str, str]:
    """Endpoint + region from env. AWS_ENDPOINT_URL set → LocalStack; unset → AWS."""
    kwargs = {"region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")}
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return kwargs


class SqsJobPublisher:
    """Async SQS publisher. One session, short-lived client per publish."""

    def __init__(self, session: AioSession | None = None) -> None:
        self._session = session or get_session()

    async def publish(self, message: JobMessage) -> None:
        name = queue_name(message.queue)
        async with self._session.create_client("sqs", **_client_kwargs()) as sqs:
            # GetQueueUrl avoids hard-coding URLs; the queue is created by bootstrap.
            resp = await sqs.get_queue_url(QueueName=name)
            await sqs.send_message(
                QueueUrl=resp["QueueUrl"],
                MessageBody=message.model_dump_json(),
            )


async def ensure_queues(
    categories: list[QueueCategory] | None = None,
    session: AioSession | None = None,
) -> dict[str, str]:
    """Idempotently create each category's main queue + DLQ with a redrive policy.

    Returns {queue_name: queue_url}. Safe to call repeatedly (CreateQueue is a
    no-op when the queue already exists with matching attributes).
    """
    cats = categories or list(QueueCategory)
    sess = session or get_session()
    created: dict[str, str] = {}
    async with sess.create_client("sqs", **_client_kwargs()) as sqs:
        for cat in cats:
            dlq = await sqs.create_queue(QueueName=dlq_name(cat))
            attrs = await sqs.get_queue_attributes(
                QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"]
            )
            dlq_arn = attrs["Attributes"]["QueueArn"]
            main = await sqs.create_queue(
                QueueName=queue_name(cat),
                Attributes={
                    "RedrivePolicy": json.dumps(
                        {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": MAX_RECEIVE_COUNT}
                    )
                },
            )
            created[queue_name(cat)] = main["QueueUrl"]
            created[dlq_name(cat)] = dlq["QueueUrl"]
            logger.info(
                "ensured queue %s (+dlq) redrive maxReceive=%d", queue_name(cat), MAX_RECEIVE_COUNT
            )
    return created
