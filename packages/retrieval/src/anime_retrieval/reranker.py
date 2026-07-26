"""Cross-encoder reranker.

The default is `cross-encoder/ms-marco-MiniLM-L-12-v2` (33M params, English-only).
It replaced `BAAI/bge-reranker-v2-m3` (568M) after a latency revisit:
measured on 20 *real* candidates (avg 962 chars — not the short
synthetic strings that hid this), warm bge takes ~6.5s on CPU. That is over 3x
the 2s RERANK_TIMEOUT, so every request timed out and fell back to hybrid order.
The advanced-RAG lift over naive retrieval measured +0.000 as a result: the whole
reranking stage was costing 2s per request and contributing nothing.

Model choice was measured, not guessed (latency on 20 real candidates, quality by
running the golden-set eval):

    model                    latency    success@1   vs baseline
    bge-reranker-v2-m3         6.46s      (n/a)     times out
    bge-reranker-base          2.07s      (n/a)     over budget
    ms-marco-MiniLM-L-6-v2     0.33s      0.636     -0.045  REGRESSION
    ms-marco-MiniLM-L-12-v2    0.63s      0.682     +0.000  <- matches baseline

L-6 is the tempting pick — it's fastest and it does restore a positive lift over
naive. But it quietly gives back a query's worth of accuracy against the frozen
baseline. L-12 costs 0.3s more and reproduces the baseline exactly, at 3x headroom
under the timeout. scripts/eval_gate.py is what caught the L-6 regression.

Weights are baked into the API image at build time (see apps/api/Dockerfile) so
`.score()` loads from local disk. Left to download lazily, the first call would
exceed RERANK_TIMEOUT and degrade retrieval until the download finished.

`uv sync` does NOT pull the weights, so unit tests stay fast as long as they
don't call `.score()` on a real BgeReranker.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

# Keep RERANKER_MODEL in sync with the model baked into apps/api/Dockerfile —
# an override that isn't baked will try to download at first request and time out.
DEFAULT_RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-12-v2")

# Truncate each (query, candidate) pair to this many tokens. Chunk texts run to
# ~1k chars; the tail contributes little relevance signal but costs quadratic
# attention time. Bounds worst-case rerank latency regardless of chunk size.
DEFAULT_MAX_LENGTH = int(os.environ.get("RERANKER_MAX_LENGTH", "512"))

# Module-level cache: same model name → same loaded model instance.
# .score() runs in a worker thread (asyncio.to_thread), so N concurrent requests
# arriving before the model is resident would each load their own copy — a
# thundering herd that wastes memory and makes every one of them miss the
# timeout. The lock collapses that to a single load; the rest wait for it.
_model_cache: dict[str, CrossEncoder] = {}
_model_lock = threading.Lock()


class Reranker(Protocol):
    """The swap-point for cross-encoder rerankers."""

    def score(self, query: str, candidates: list[str]) -> list[float]:
        """Return per-candidate relevance scores. Higher = more relevant."""
        ...

    def warm(self) -> None:
        """Load the model into memory. Call before serving; see BgeReranker.warm."""
        ...


class BgeReranker:
    """Lazy-loading wrapper around sentence_transformers.CrossEncoder."""

    def __init__(
        self,
        model_name: str = DEFAULT_RERANKER_MODEL,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length

    def _get_model(self) -> CrossEncoder:
        # Fast path: already resident, no lock.
        model = _model_cache.get(self._model_name)
        if model is not None:
            return model
        with _model_lock:
            # Re-check: another thread may have loaded it while we waited.
            model = _model_cache.get(self._model_name)
            if model is None:
                from sentence_transformers import CrossEncoder

                model = CrossEncoder(self._model_name, max_length=self._max_length)
                _model_cache[self._model_name] = model
        return model

    def warm(self) -> None:
        """Load the model into memory ahead of the first real query.

        A cold load takes ~2s — on par with RERANK_TIMEOUT itself, so the first
        query of an un-warmed process reranks nothing and silently degrades to
        hybrid order. Every entrypoint that scores must warm first: the API does
        it in lifespan (before readiness flips green), and the eval harness does
        it before scoring — otherwise eval measures a cold pipeline that
        production never actually runs, and under-reports the reranker's lift.
        """
        self.score("warmup", ["warmup"])

    def score(self, query: str, candidates: list[str]) -> list[float]:
        if not candidates:
            return []
        model = self._get_model()
        pairs = [(query, c) for c in candidates]
        # sentence-transformers v5.x stubs are over-strict and reject the
        # documented `list[tuple[str, str]]` input; runtime accepts it fine.
        scores = model.predict(pairs)  # type: ignore[arg-type]
        return [float(s) for s in scores]

    @property
    def model_name(self) -> str:
        return self._model_name
