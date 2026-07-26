"""reembed.corpus handler — re-run ingestion for a corpus CSV.

Wraps the existing anime_ingestion.ingest() pipeline, which is already
idempotent (delete+insert per mal_id). Triggered when the corpus changes or the
embedding model is swapped (embedding-model change).

`ingest_fn` is injectable so unit tests assert the wiring without spending OpenAI
$ or needing a DB; production uses the real ingest + OpenAIEmbedder.

Spends OpenAI tokens → only exercised live via the integration path.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from anime_worker.handlers.base import HandlerContext

logger = logging.getLogger(__name__)

# (session, csv_path, embedder) -> stats dict. Matches anime_ingestion.ingest.
IngestFn = Callable[..., Awaitable[dict[str, Any]]]


def _default_ingest() -> IngestFn:
    from anime_ingestion.indexer import ingest

    return ingest


async def handle_reembed_corpus(
    payload: dict[str, Any],
    ctx: HandlerContext,
    *,
    ingest_fn: IngestFn | None = None,
) -> None:
    csv_path = payload.get("csv_path")
    if not csv_path:
        raise ValueError("reembed.corpus requires a 'csv_path' in the payload")

    ingest = ingest_fn or _default_ingest()
    # Build the embedder lazily (needs OPENAI_API_KEY) so test injection avoids it.
    from anime_core.embeddings import OpenAIEmbedder

    embedder = OpenAIEmbedder()
    async with ctx.session_factory() as session:
        stats = await ingest(
            session=session,
            csv_path=csv_path,
            embedder=embedder,
            measure_per_query_latency=False,
        )
    logger.info("reembed.corpus done: %s", stats)
