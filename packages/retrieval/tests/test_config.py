"""Tests for retrieval config resolution (no DB / no API key needed)."""

from __future__ import annotations

import pytest
from anime_retrieval.pipeline import DEFAULT_MMR_LAMBDA, resolve_mmr_lambda


def test_default_is_085() -> None:
    assert DEFAULT_MMR_LAMBDA == 0.85


def test_resolve_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMR_LAMBDA", raising=False)
    assert resolve_mmr_lambda() == DEFAULT_MMR_LAMBDA


def test_resolve_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MMR_LAMBDA", "0.9")
    assert resolve_mmr_lambda() == 0.9


def test_explicit_arg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MMR_LAMBDA", "0.5")
    assert resolve_mmr_lambda(0.3) == 0.3
