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

Input LENGTH was then measured the same way — same 20 real candidates (avg 962
chars), same golden set, same gate. `max_length` caps each (query, candidate)
pair, and attention cost grows faster than linearly in sequence length, so it is
the cheapest lever available:

    max_length   latency   success@1   lift over naive   vs baseline
    512            0.91s     0.653          +0.050         +0.000   (the old default)
    256            0.66s     0.653          +0.050         +0.000   <- 28% faster, same quality
    128            0.28s     0.604          +0.000         -0.050   REGRESSION

At 128 the advanced pipeline scores exactly what NAIVE retrieval scores: the
reranking stage stops contributing anything at all while still costing time.
256 is the floor that still pays for itself, and it is what buys the headroom
this stage was missing (p95 compute 1.84s -> ~1.3s against a 2.0s timeout).

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
import time
from typing import TYPE_CHECKING, Protocol

from anime_core.observability.metrics import record_rerank_compute

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

# Keep RERANKER_MODEL in sync with the model baked into apps/api/Dockerfile —
# an override that isn't baked will try to download at first request and time out.
DEFAULT_RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-12-v2")

# Truncate each (query, candidate) pair to this many tokens. Chunk texts run to
# ~1k chars; the tail contributes little relevance signal but costs quadratic
# attention time. Bounds worst-case rerank latency regardless of chunk size.
#
# 256, not 512, and the difference was measured rather than reasoned about: the
# golden-set gate scores IDENTICALLY at both (success@1 0.653, lift over naive
# +0.050) while 256 is 28% faster, which is what takes this stage from 85% of its
# 2.0s timeout down to roughly two thirds. Do not push it to 128 -- there the
# advanced pipeline scores exactly what naive retrieval scores, i.e. reranking
# costs time and buys nothing. See the table in the module docstring.
DEFAULT_MAX_LENGTH = int(os.environ.get("RERANKER_MAX_LENGTH", "256"))

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

        Deliberately bypasses score(): a 1-candidate warmup is not a rerank (real
        ones score 20) and recording it would drag the low percentiles of
        anime.retrieval.rerank.compute down once per process.
        """
        model = self._get_model()
        model.predict([("warmup", "warmup")])

    def score(self, query: str, candidates: list[str]) -> list[float]:
        if not candidates:
            return []
        # _get_model() is OUTSIDE the timer on purpose: the first call loads weights
        # (~0.69s measured) and that one-off cost would sit in p99 forever, which is
        # the opposite of what this metric is for.
        model = self._get_model()
        pairs = [(query, c) for c in candidates]
        # sentence-transformers v5.x stubs are over-strict and reject the
        # documented `list[tuple[str, str]]` input; runtime accepts it fine.
        started = time.perf_counter()
        scores = model.predict(pairs)  # type: ignore[arg-type]
        # The honest cost of the model, measured where the work happens rather than
        # across an await. See metrics.record_rerank_compute for why that matters.
        record_rerank_compute(time.perf_counter() - started)
        return [float(s) for s in scores]

    @property
    def model_name(self) -> str:
        return self._model_name
