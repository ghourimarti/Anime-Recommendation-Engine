#!/usr/bin/env python
"""Brutal full-stack inspection for the sglang chain: sglang -> groq -> openai.

One command, every component: containers, data tier, both cache layers, the
retrieval stage chain, venue routing, LLM serving, answer kinds, safety,
NFRs, observability, cost controls and circuit breakers.

Identical to inspect_stack_vllm.py except for the engine this chain
expects. The checks live in _inspect_sections.py so the two can never drift into
testing different contracts while appearing to test one.

  python scripts/inspect_stack_sglang.py
  python scripts/inspect_stack_sglang.py --section router --section retrieval
  python scripts/inspect_stack_sglang.py --no-probe    # read-only
  python scripts/inspect_stack_sglang.py --selftest    # prove the checks can fail

Exit code is the number of FAILs, so it doubles as a gate.

Requires the SGLANG engine to be the one holding the GPU:  make up-sglang
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _inspect_common import main
from _inspect_sections import SECTIONS

if __name__ == "__main__":
    raise SystemExit(main("sglang", SECTIONS))
