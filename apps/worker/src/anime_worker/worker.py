"""The worker consumer loop.

Split into a pure-ish, unit-testable `process_message` (idempotency + dispatch,
no SQS) and the aiobotocore long-poll `run_worker` that wraps it. The split lets
us test the delivery semantics (dedup, dispatch, no-delete-on-failure) without a
broker.

Delivery semantics:
  - receive (long poll) → for each message:
      • parse. An unparseable body is POISON — see below.
      • idempotency: set_nx(seen:{key}). If the key already existed, this is a
        redelivery of an ALREADY-PROCESSED message → delete + skip.
      • dispatch to the handler by JobType.
      • success → delete the message.
      • failure → DON'T delete (SQS redelivers; after maxReceiveCount → DLQ) AND
        clear the seen key so the retry actually re-runs (a transient failure must
        not be permanently deduped away).
  Handlers are idempotent, so a rare concurrent double-delivery is harmless.

Two failure classes, deliberately handled differently:

  TRANSIENT (handler raised) — the same message may well succeed on retry, so we
  leave it on the queue and let SQS redrive it. After maxReceiveCount it DLQs.

  POISON (body doesn't parse) — no number of retries will make malformed bytes
  valid. Retrying is pure waste, so we publish it straight to the DLQ (with the
  parse error attached) and delete it from the source queue.

  Getting this wrong is what took the worker down: the parse used to sit OUTSIDE
  the try block, so a single malformed body raised out of process_message, out of
  the receive loop, and killed the process. The message was never deleted, so the
  restarted worker received it again and died again — a crash loop in which ONE
  bad message blocked every other job on the queue. A poison message must never
  be able to take down the consumer.

Deploy order note: because a body we can't parse goes to the DLQ immediately, roll
WORKERS BEFORE PRODUCERS. Otherwise a producer emitting a new schema can briefly
outrun the consumers that understand it, and those messages DLQ instead of
waiting. If that happens, the DLQ is inspectable and the redrive runbook replays
them — nothing is lost, but the ordering avoids the noise.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from enum import Enum, auto
from typing import Any

from anime_core.cache import Cache
from anime_core.jobs import JobMessage, JobType, QueueCategory
from anime_core.observability.metrics import record_job, record_poison_message
from anime_core.sqs import _client_kwargs, dlq_name, queue_name
from pydantic import ValidationError

from anime_worker.handlers.base import Handler, HandlerContext
from anime_worker.registry import REGISTRY

logger = logging.getLogger(__name__)

SEEN_TTL_SECONDS = 7 * 24 * 3600  # dedup window; comfortably outlives redelivery + DLQ
RECEIVE_WAIT_SECONDS = 20  # SQS long-poll (fewer empty receives, lower cost)
RECEIVE_BATCH = 10


def _summarize_validation_error(exc: ValidationError) -> str:
    """Field paths + error types only — never the values.

    A malformed body is still a body: it can carry user content. Logging the raw
    message to diagnose a parse failure would leak exactly the PII the redaction
    layer exists to keep out of logs. The field path and error type are enough to
    debug a schema mismatch, and they're safe.
    """
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['type']}" for e in exc.errors()[:5]
    )


class ProcessResult(Enum):
    PROCESSED = auto()
    DUPLICATE = auto()
    FAILED = auto()
    POISON = auto()


async def process_message(
    raw_body: str,
    *,
    cache: Cache,
    ctx: HandlerContext,
    registry: dict[JobType, Handler] | None = None,
) -> ProcessResult:
    """Idempotency gate + dispatch for one message body. No SQS here.

    Returns PROCESSED (delete it), DUPLICATE (delete it — already done),
    FAILED (do NOT delete — let SQS redrive), or POISON (unparseable — DLQ it
    now; retrying malformed bytes can only ever fail again).

    This function must NEVER raise. Whatever it is handed — truncated JSON, an
    unknown job type, a handler that blows up — it has to come back with a verdict,
    because the caller is the receive loop and an exception there kills the worker.
    """
    reg = registry if registry is not None else REGISTRY

    try:
        message = JobMessage.model_validate_json(raw_body)
    except ValidationError as exc:
        # Malformed body: bad JSON, missing fields, unknown job type. No retry can
        # fix it, and letting it raise here is what crash-looped the worker.
        logger.error(
            "poison message (%d bytes): %s; routing to DLQ, not retrying",
            len(raw_body),
            _summarize_validation_error(exc),
        )
        record_poison_message(queue=os.environ.get("WORKER_QUEUE", "unknown"))
        return ProcessResult.POISON

    seen_key = f"seen:{message.idempotency_key}"
    is_new = await cache.set_nx(seen_key, "1", ttl_seconds=SEEN_TTL_SECONDS)
    if not is_new:
        logger.info("duplicate job %s (%s); skipping", message.idempotency_key, message.type)
        return ProcessResult.DUPLICATE

    handler = reg.get(message.type)
    if handler is None:
        # The type parsed, so this worker's JobType enum knows it — but no handler
        # is registered for it. Enum and registry ship in the same image, so this
        # is a permanent registry gap in this build, not a transient fault.
        # Redelivering it 5 times cannot conjure a handler; DLQ it now.
        logger.error("no handler registered for job type %s; routing to DLQ", message.type)
        record_poison_message(queue=os.environ.get("WORKER_QUEUE", "unknown"))
        return ProcessResult.POISON

    try:
        await handler(message.payload, ctx)
        return ProcessResult.PROCESSED
    except Exception:
        logger.warning("handler for %s failed; will redeliver", message.type, exc_info=True)
        # Clear the dedup marker so the retry actually re-runs this message
        # (a transient failure must not be permanently deduped away).
        await cache.delete(seen_key)
        return ProcessResult.FAILED


async def run_worker(
    category: QueueCategory,
    *,
    cache: Cache,
    ctx: HandlerContext,
    stop_event: asyncio.Event | None = None,
    session_factory: Any = None,
) -> None:
    """Long-poll the category's queue and process messages until stop_event is set."""
    from aiobotocore.session import get_session

    stop = stop_event or asyncio.Event()
    name = queue_name(category)
    aio = get_session()

    async with aio.create_client("sqs", **_client_kwargs()) as sqs:
        url = (await sqs.get_queue_url(QueueName=name))["QueueUrl"]
        dlq_url = (await sqs.get_queue_url(QueueName=dlq_name(category)))["QueueUrl"]
        logger.info("worker polling %s", name)
        while not stop.is_set():
            resp = await sqs.receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=RECEIVE_BATCH,
                WaitTimeSeconds=RECEIVE_WAIT_SECONDS,
            )
            for msg in resp.get("Messages", []):
                # Belt and braces. process_message is written not to raise, but this
                # loop is the worker's life: ANY escaping exception here — including
                # one from the SQS calls below — kills the process, and the message
                # (still on the queue) kills it again on restart. One bad message must
                # never be able to stop the consumer. Nothing gets to leave this loop.
                try:
                    result = await process_message(msg["Body"], cache=cache, ctx=ctx)

                    if result is ProcessResult.POISON:
                        # Unprocessable by construction. Hand it to the DLQ ourselves
                        # rather than burning maxReceiveCount redeliveries first, then
                        # delete it so it can't come back and stall the queue behind it.
                        await sqs.send_message(QueueUrl=dlq_url, MessageBody=msg["Body"])
                        await sqs.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
                    elif result in (ProcessResult.PROCESSED, ProcessResult.DUPLICATE):
                        await sqs.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
                    # FAILED → leave it; SQS redelivers, then DLQs after maxReceiveCount.

                    record_job(queue=category.value, outcome=result.name.lower())
                except Exception:
                    logger.exception("unexpected error handling a message; leaving it for redrive")
                    record_job(queue=category.value, outcome="error")


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Graceful shutdown: SIGTERM/SIGINT set the stop event so the loop drains."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Windows' ProactorEventLoop lacks add_signal_handler — ignore there.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)


def worker_queue_from_env() -> QueueCategory:
    raw = os.environ.get("WORKER_QUEUE", QueueCategory.FEEDBACK.value)
    return QueueCategory(raw)
