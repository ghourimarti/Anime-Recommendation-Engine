"""Reranker model-loading tests — never load a real cross-encoder (slow, network)."""

from __future__ import annotations

import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest
from anime_retrieval import reranker as rr


@pytest.fixture(autouse=True)
def _clear_model_cache() -> None:
    rr._model_cache.clear()


def _install_fake_cross_encoder(monkeypatch: pytest.MonkeyPatch, load_delay: float = 0.0):  # type: ignore[no-untyped-def]
    """Stub sentence_transformers.CrossEncoder and count how often it is constructed."""
    calls: list[str] = []

    class FakeCrossEncoder:
        def __init__(self, model_name: str, max_length: int | None = None) -> None:
            calls.append(model_name)
            self.max_length = max_length
            time.sleep(load_delay)  # simulate a slow cold load

        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            return [float(len(c)) for _, c in pairs]

    fake = ModuleType("sentence_transformers")
    fake.CrossEncoder = FakeCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    return SimpleNamespace(calls=calls)


def test_scores_align_with_candidate_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_cross_encoder(monkeypatch)
    scores = rr.BgeReranker().score("q", ["a", "bbb", "cc"])
    assert scores == [1.0, 3.0, 2.0]


def test_empty_candidates_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _install_fake_cross_encoder(monkeypatch)
    assert rr.BgeReranker().score("q", []) == []
    assert spy.calls == []  # must not even load the model


def test_max_length_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_cross_encoder(monkeypatch)
    r = rr.BgeReranker(max_length=128)
    r.warm()
    assert rr._model_cache[r.model_name].max_length == 128


def test_concurrent_first_calls_load_the_model_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: an unlocked lazy load let every concurrent request load its own copy.

    .score() runs via asyncio.to_thread, so N requests hitting a cold process each
    entered the load — a thundering herd that wasted memory and made all of them
    blow RERANK_TIMEOUT. The double-checked lock must collapse this to one load.
    """
    spy = _install_fake_cross_encoder(monkeypatch, load_delay=0.15)
    r = rr.BgeReranker()
    barrier = threading.Barrier(8)

    def hit() -> None:
        barrier.wait()  # maximize the race
        r.score("q", ["candidate"])

    threads = [threading.Thread(target=hit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert spy.calls == [rr.DEFAULT_RERANKER_MODEL], f"model loaded {len(spy.calls)}x, want 1x"


def test_warm_makes_the_model_resident(monkeypatch: pytest.MonkeyPatch) -> None:
    """warm() must fully load the model, so the first real query pays no cold-load cost."""
    spy = _install_fake_cross_encoder(monkeypatch)
    r = rr.BgeReranker()
    r.warm()
    assert len(spy.calls) == 1
    r.score("q", ["a", "b"])
    assert len(spy.calls) == 1  # still 1 — served from cache, no reload
