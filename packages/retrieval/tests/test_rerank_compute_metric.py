"""I.F1b: the compute metric must measure the MODEL, not its surroundings.

The bug this guards against is not a crash — it is a number that looks right and
means something else. anime.retrieval.stage.duration{stage="rerank"} spans an
`await`, so it reports thread handoff + model + event-loop rescheduling as one
figure. Measured in production: model 0.056s, that figure 1.250s p50. Three
separate "make the reranker faster" proposals were aimed at a component that
accounted for ~4% of the number.

These tests assert the metric FIRES and what it EXCLUDES. They deliberately do not
assert on durations, which would be flaky and would prove nothing anyway.
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest
from anime_retrieval import reranker as rr


@pytest.fixture(autouse=True)
def _clear_model_cache() -> None:
    rr._model_cache.clear()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture every record_rerank_compute call."""
    seen: list[float] = []
    monkeypatch.setattr(rr, "record_rerank_compute", seen.append)
    return seen


def _fake_cross_encoder(monkeypatch: pytest.MonkeyPatch, load_delay: float = 0.0) -> None:
    import time as _t

    class FakeCrossEncoder:
        def __init__(self, model_name: str, max_length: int | None = None) -> None:
            _t.sleep(load_delay)

        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            return [float(len(c)) for _, c in pairs]

    fake = ModuleType("sentence_transformers")
    fake.CrossEncoder = FakeCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def test_score_records_exactly_one_compute_sample(
    monkeypatch: pytest.MonkeyPatch, recorded: list[float]
) -> None:
    _fake_cross_encoder(monkeypatch)
    rr.BgeReranker().score("q", ["a", "bb", "ccc"])
    assert len(recorded) == 1, "one rerank == one compute sample"


def test_warm_records_nothing(monkeypatch: pytest.MonkeyPatch, recorded: list[float]) -> None:
    """A 1-candidate warmup is not a rerank.

    Real reranks score 20 candidates. Letting warm() through would add one
    unrepresentative low sample per process and drag the low percentiles down
    exactly where we are trying to read them.
    """
    _fake_cross_encoder(monkeypatch)
    rr.BgeReranker().warm()
    assert recorded == []


def test_empty_candidates_record_nothing(
    monkeypatch: pytest.MonkeyPatch, recorded: list[float]
) -> None:
    _fake_cross_encoder(monkeypatch)
    assert rr.BgeReranker().score("q", []) == []
    assert recorded == []


def test_compute_excludes_model_load(
    monkeypatch: pytest.MonkeyPatch, recorded: list[float]
) -> None:
    """The one-off ~0.69s weight load must never enter the histogram.

    _get_model() sits outside the timer on purpose. If it drifted inside, the first
    call of every process would plant a huge sample in p99 and the metric would
    permanently misrepresent steady-state cost.
    """
    _fake_cross_encoder(monkeypatch, load_delay=0.30)
    rr.BgeReranker().score("q", ["a"])
    assert len(recorded) == 1
    assert recorded[0] < 0.30, (
        f"compute {recorded[0]:.3f}s includes the 0.30s model load — "
        "_get_model() has drifted inside the timer"
    )


def test_scores_unchanged_by_instrumentation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Observational change: behaviour must be byte-identical."""
    _fake_cross_encoder(monkeypatch)
    assert rr.BgeReranker().score("q", ["a", "bbb", "cc"]) == [1.0, 3.0, 2.0]
