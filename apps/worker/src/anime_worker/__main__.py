"""Worker entrypoint:  python -m anime_worker [--queue feedback|ingestion|housekeeping]

Wires structured logging, the shared cache + DB session factory, ensures
its queue exists (defensive — the sqs-init one-shot normally creates them), and
runs the long-poll loop until SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from anime_core.cache import get_cache
from anime_core.db.engine import session_scope
from anime_core.jobs import QueueCategory
from anime_core.observability import configure_logging
from anime_core.sqs import ensure_queues
from dotenv import load_dotenv

from anime_worker.handlers.base import HandlerContext
from anime_worker.worker import install_signal_handlers, run_worker, worker_queue_from_env


async def _amain(category: QueueCategory) -> None:
    cache = get_cache()
    ctx = HandlerContext(cache=cache, session_factory=session_scope)
    # Defensive: make sure this category's queue + DLQ exist before polling.
    await ensure_queues([category])

    stop = asyncio.Event()
    install_signal_handlers(stop)
    await run_worker(category, cache=cache, ctx=ctx, stop_event=stop)


def main() -> None:
    load_dotenv()
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="Anime async SQS worker.")
    parser.add_argument(
        "--queue",
        choices=[c.value for c in QueueCategory],
        default=None,
        help="Queue category to consume. Defaults to $WORKER_QUEUE or 'feedback'.",
    )
    args = parser.parse_args()
    category = QueueCategory(args.queue) if args.queue else worker_queue_from_env()
    asyncio.run(_amain(category))


if __name__ == "__main__":
    main()
