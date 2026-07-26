"""Golden eval set: schema + loader.

A golden query pairs a natural-language preference with the set of anime
(mal_ids) a good retriever should surface. `query_type` lets us slice metrics:

  - clear:       one obvious target; tests basic relevance
  - edge:        a franchise (sequels/movies); tests recall across related titles
                 and that dedup-by-anime still surfaces the franchise
  - vague:       fuzzy preference with several acceptable answers
  - adversarial: out-of-scope or injection canary; expected_mal_ids is empty,
                 success = NOT confidently recommending irrelevant content
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

QueryType = Literal["clear", "edge", "vague", "adversarial"]


class GoldenQuery(BaseModel):
    """One curated (query, expected anime) pair."""

    id: str
    query: str
    query_type: QueryType
    expected_mal_ids: list[int] = Field(default_factory=list)
    notes: str = ""

    @property
    def is_adversarial(self) -> bool:
        return self.query_type == "adversarial"


def load_golden_set(path: Path | str | None = None) -> list[GoldenQuery]:
    """Load a golden set from a .jsonl file.

    Defaults to the packaged `golden_sets/v1.jsonl`. Pass an explicit path to
    load a different version.
    """
    if path is None:
        ref = resources.files("anime_eval").joinpath("golden_sets/v1.jsonl")
        text = ref.read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")

    queries: list[GoldenQuery] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Golden set line {line_no} is not valid JSON: {exc}") from exc
        queries.append(GoldenQuery.model_validate(data))

    ids = [q.id for q in queries]
    if len(ids) != len(set(ids)):
        raise ValueError("Golden set contains duplicate query ids")
    return queries
