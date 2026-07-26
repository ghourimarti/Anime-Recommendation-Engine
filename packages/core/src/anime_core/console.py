"""Console output helpers.

`use_utf8_stdout()` exists because Windows still defaults stdout to cp1252, which
cannot encode the characters our CLI output actually uses. `make eval` printed its
metrics table, reached the first "↑" in the delta column, and died:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2191'

Exit code 1. A green run that regressed nothing looked exactly like a failed one, on
the single command a developer is most likely to run before shipping a retrieval
change — and CI (Linux, UTF-8) never saw it, so the only person it broke was whoever
was doing the right thing locally.

This helper was already open-coded in five places (compare.py and four scripts) and
missing from the two CLIs that actually crashed. One implementation, imported.
"""

from __future__ import annotations

import contextlib
import sys


def use_utf8_stdout() -> None:
    """Force stdout/stderr to UTF-8 so non-ASCII output can't kill the process.

    Best-effort: some environments wrap the streams in objects without
    .reconfigure (pytest's capture, for one). Those paths write strings without
    hitting the encoding step anyway, so suppressing is correct rather than lazy.

    Call this FIRST in any entrypoint that prints non-ASCII — arrows, box drawing,
    emoji, or user content, which on a corpus of anime titles is guaranteed to include
    Japanese at some point.
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
