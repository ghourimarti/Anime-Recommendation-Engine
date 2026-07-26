"""Worker delivery-semantics tests — no SQS, no DB.

Exercises process_message: dispatch routing, idempotency dedup, and the
no-delete-on-failure contract that drives SQS redrive → DLQ.
"""

from __future__ import annotations

from typing import Any

import pytest
from anime_core.cache import InMemoryCache
from anime_core.jobs import JobMessage, JobType
from anime_worker.handlers.base import Handler, HandlerContext
from anime_worker.worker import ProcessResult, process_message


def _ctx() -> HandlerContext:
    return HandlerContext(cache=InMemoryCache(), session_factory=None)


def _registry(record: list[str], *, fail: bool = False) -> dict[JobType, Handler]:
    async def handler(payload: dict[str, Any], ctx: HandlerContext) -> None:
        record.append(payload.get("tag", "?"))
        if fail:
            raise RuntimeError("boom")

    return {JobType.FEEDBACK_RECORDED: handler}


@pytest.mark.asyncio
async def test_processes_and_dispatches() -> None:
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    calls: list[str] = []
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED, payload={"tag": "a"}, idempotency_key="k1")
    result = await process_message(
        msg.model_dump_json(), cache=cache, ctx=ctx, registry=_registry(calls)
    )
    assert result is ProcessResult.PROCESSED
    assert calls == ["a"]


@pytest.mark.asyncio
async def test_duplicate_is_skipped() -> None:
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    calls: list[str] = []
    reg = _registry(calls)
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED, payload={"tag": "a"}, idempotency_key="dup")
    body = msg.model_dump_json()

    first = await process_message(body, cache=cache, ctx=ctx, registry=reg)
    second = await process_message(body, cache=cache, ctx=ctx, registry=reg)

    assert first is ProcessResult.PROCESSED
    assert second is ProcessResult.DUPLICATE
    assert calls == ["a"]  # handler ran exactly once despite two deliveries


@pytest.mark.asyncio
async def test_failure_does_not_dedup_so_retry_runs() -> None:
    """A handler that raises must NOT leave the dedup marker set — else the SQS
    redelivery would be skipped and the message lost before reaching the DLQ."""
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    calls: list[str] = []
    msg = JobMessage(type=JobType.FEEDBACK_RECORDED, payload={"tag": "a"}, idempotency_key="retry")
    body = msg.model_dump_json()

    first = await process_message(body, cache=cache, ctx=ctx, registry=_registry(calls, fail=True))
    assert first is ProcessResult.FAILED
    # The redelivery (now with a succeeding handler) must actually re-run.
    second = await process_message(body, cache=cache, ctx=ctx, registry=_registry(calls))
    assert second is ProcessResult.PROCESSED
    assert calls == ["a", "a"]


@pytest.mark.asyncio
async def test_unknown_type_goes_straight_to_dlq() -> None:
    """A valid type with no registered handler is a permanent gap, not a transient fault.

    Enum and registry ship in the same image, so no amount of redelivery will
    produce a handler. Don't burn maxReceiveCount discovering that — DLQ it now.
    """
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    msg = JobMessage(type=JobType.REEMBED_CORPUS, idempotency_key="u1")
    result = await process_message(msg.model_dump_json(), cache=cache, ctx=ctx, registry={})
    assert result is ProcessResult.POISON


# ── poison messages: the crash-loop regression ───────────────────────────────


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("", "empty body"),
        ("not json at all", "not JSON"),
        ("{", "truncated JSON"),
        ('{"type": "feedback_recorded"', "unterminated object"),
        ("[]", "JSON array, not an object"),
        ("null", "JSON null"),
        ('{"type": "no_such_type", "idempotency_key": "k"}', "unknown job type"),
        ('{"payload": {}, "idempotency_key": "k"}', "missing required 'type'"),
        # Right type, wrong spelling: the wire value is "feedback.recorded", dotted.
        # An underscore is exactly the kind of near-miss a producer typo produces.
        ('{"type": "feedback_recorded", "idempotency_key": "k"}', "enum near-miss"),
        ('{"type": 42, "idempotency_key": "k"}', "type is the wrong JSON type"),
        ('😀 {"type": "feedback.recorded"}', "leading garbage"),
    ],
)
@pytest.mark.asyncio
async def test_poison_message_never_raises(body: str, why: str) -> None:
    """THE regression test for the worker crash loop.

    process_message used to call JobMessage.model_validate_json OUTSIDE the try
    block. A malformed body raised ValidationError straight through the receive
    loop and killed the process. Because the message was never deleted, the
    restarted worker picked it up and died again — a crash loop in which a single
    bad message blocked every other job on the queue (observed: RestartCount=5).

    So the contract is absolute: whatever bytes arrive, process_message RETURNS a
    verdict. It does not raise. If this test ever fails, the worker can be taken
    down by anyone who can put a message on the queue.
    """
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    calls: list[str] = []

    result = await process_message(body, cache=cache, ctx=ctx, registry=_registry(calls))

    assert result is ProcessResult.POISON, f"{why!r} should be POISON, got {result}"
    assert calls == [], "a message that doesn't parse must never reach a handler"


@pytest.mark.asyncio
async def test_poison_message_does_not_block_the_next_good_one() -> None:
    """Head-of-line blocking check: the poison message is what took the queue down.

    A bad message must be isolated to itself — the very next valid message has to
    process normally, in the same worker, without a restart.
    """
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    calls: list[str] = []
    reg = _registry(calls)

    assert await process_message("{{{ garbage", cache=cache, ctx=ctx, registry=reg) is (
        ProcessResult.POISON
    )

    good = JobMessage(type=JobType.FEEDBACK_RECORDED, payload={"tag": "ok"}, idempotency_key="k9")
    assert (
        await process_message(good.model_dump_json(), cache=cache, ctx=ctx, registry=reg)
        is ProcessResult.PROCESSED
    )
    assert calls == ["ok"]


@pytest.mark.asyncio
async def test_poison_message_is_not_logged_verbatim(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed body is still a body — it can carry user content.

    Dumping the raw message to diagnose a parse failure would leak exactly the PII
    the redaction layer exists to keep out of logs. Log the field path and error
    type; never the values.
    """
    cache = InMemoryCache()
    ctx = HandlerContext(cache=cache, session_factory=None)
    secret = "user@example.com"
    # Bad enum value, and a payload carrying PII alongside it.
    body = f'{{"type": "bogus_type", "payload": {{"email": "{secret}"}}}}'

    with caplog.at_level("ERROR"):
        result = await process_message(body, cache=cache, ctx=ctx, registry={})

    assert result is ProcessResult.POISON
    assert secret not in caplog.text, "the raw body leaked into the logs"
    assert "type" in caplog.text  # the offending FIELD is named — that's the debuggable part
