"""OpenAI embeddings client with batching, retries, and latency measurement.

`text-embedding-3-small`, 1536-dim.
Original pick was `text-embedding-3-large` (3072-dim), but per-query embedding
p50 exceeded the 300 ms gate (399 ms measured) — network RTT to OpenAI's US
servers is a structural floor at this network distance. `text-embedding-3-small`
has genuinely lower server-side processing time (~100-150 ms less), bringing p50
into the WARN/PASS range. Re-evaluate with the RAGAS eval set — if context recall
degrades, switch back to 3-large and accept the added latency. Used by:
  - Ingestion (embed the corpus): anime_ingestion.indexer
  - Retrieval (embed user queries):  anime_retrieval.pipeline

Lives in anime_core so both packages depend on a single embedder definition
without anime_retrieval needing to import from anime_ingestion.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass

from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 96


@dataclass(frozen=True)
class EmbedResult:
    """Returned by `OpenAIEmbedder.embed`."""

    embeddings: list[list[float]]
    total_tokens: int
    latency_seconds: float


class OpenAIEmbedder:
    """Thin async client around OpenAI's embeddings API.

    Retries transient API errors with exponential backoff (tenacity).
    """

    def __init__(self, *, api_key: str | None = None, model: str = EMBEDDING_MODEL) -> None:
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it.")
        self._client = AsyncOpenAI(api_key=resolved_key)
        self._model = model

    async def embed(self, texts: Sequence[str]) -> EmbedResult:
        """Embed a sequence of texts; returns vectors in the same order."""
        all_embeddings: list[list[float]] = []
        total_tokens = 0
        start = time.perf_counter()

        for i in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[i : i + BATCH_SIZE])
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(OpenAIAPIError),
                reraise=True,
            ):
                with attempt:
                    resp = await self._client.embeddings.create(
                        input=batch,
                        model=self._model,
                    )
            all_embeddings.extend(d.embedding for d in resp.data)
            total_tokens += resp.usage.total_tokens

        elapsed = time.perf_counter() - start
        return EmbedResult(
            embeddings=all_embeddings,
            total_tokens=total_tokens,
            latency_seconds=elapsed,
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM
