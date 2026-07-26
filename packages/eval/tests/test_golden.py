"""Tests for the golden-set loader + the packaged v1 golden set."""

from __future__ import annotations

import pytest
from anime_eval.golden import GoldenQuery, load_golden_set


def test_packaged_golden_set_loads() -> None:
    golden = load_golden_set()
    assert len(golden) >= 20, "v1 golden set should have at least 20 queries"
    assert all(isinstance(q, GoldenQuery) for q in golden)


def test_golden_ids_unique() -> None:
    golden = load_golden_set()
    ids = [q.id for q in golden]
    assert len(ids) == len(set(ids))


def test_golden_query_types_valid() -> None:
    golden = load_golden_set()
    valid = {"clear", "edge", "vague", "adversarial"}
    assert all(q.query_type in valid for q in golden)


def test_non_adversarial_have_expected_ids() -> None:
    golden = load_golden_set()
    for q in golden:
        if not q.is_adversarial:
            assert q.expected_mal_ids, f"{q.id} ({q.query_type}) must have expected ids"


def test_adversarial_have_empty_expected() -> None:
    golden = load_golden_set()
    adversarial = [q for q in golden if q.is_adversarial]
    assert adversarial, "golden set should include adversarial canaries"
    assert all(q.expected_mal_ids == [] for q in adversarial)


def test_loader_rejects_bad_json(tmp_path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x"\n', encoding="utf-8")  # malformed
    with pytest.raises(ValueError, match="not valid JSON"):
        load_golden_set(bad)


def test_loader_rejects_duplicate_ids(tmp_path) -> None:
    dupe = tmp_path / "dupe.jsonl"
    line = '{"id": "q1", "query": "x", "query_type": "clear", "expected_mal_ids": [1]}'
    dupe.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate query ids"):
        load_golden_set(dupe)
