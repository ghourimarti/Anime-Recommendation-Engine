#!/usr/bin/env python3
"""Venue benchmark harness — TTFT / TPOT / output throughput.

Measures any OpenAI-compatible chat-completions endpoint. Deliberately knows
nothing about which engine is behind it: vLLM (S19.6) and SGLang (S20.5) are
measured by this same code against the same prompt fixture, so the engine is
the only variable. An engine-specific harness would void the comparison.

Metric definitions (these are easy to get subtly wrong):
    TTFT  time from request sent to the FIRST streamed token.
          Requires streaming; a non-streaming request cannot measure it.
    TPOT  mean inter-token latency AFTER the first token:
              (e2e - ttft) / (output_tokens - 1)
          NOT total/tokens — that double-counts TTFT.
    tok/s output tokens divided by generation time (e2e - ttft), i.e. the
          decode rate, excluding prefill.

Warm-up runs are discarded: the first request triggers CUDA graph capture and
cache warming, and including it makes whichever engine is measured first look
artificially slow.

Usage:
    python scripts/bench_venue.py --engine vllm
    python scripts/bench_venue.py --engine sglang          # -> http://localhost:1020/v1
    python scripts/bench_venue.py --url http://localhost:9000/v1
    python scripts/bench_venue.py --runs 30 --warmup 3

Exit codes:
    0  benchmark completed, results written
    1  endpoint unreachable or all runs failed
    2  usage error
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx is required:  uv pip install httpx", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = REPO_ROOT / "scripts" / "venue" / "prompts.json"
DEFAULT_OUT_DIR = REPO_ROOT / "Documents" / "docs" / "venue-bench"


@dataclass
class RunResult:
    prompt_index: int
    ttft_ms: float
    e2e_ms: float
    output_tokens: int
    tpot_ms: float | None
    output_tok_s: float | None


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile. Honest for the small N we run here."""
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[idx]


def gpu_snapshot() -> dict[str, object]:
    """Record GPU state so a result file is reproducible-in-context.

    Two runs at different desktop memory pressure are not comparable; capturing
    free VRAM makes that visible later instead of mysterious.
    """
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        name, total, free = (part.strip() for part in out.split(",")[:3])
        return {"name": name, "memory_total_mib": int(total), "memory_free_mib": int(free)}
    except Exception as exc:  # nvidia-smi absent, CPU-only box, etc.
        return {"error": f"{type(exc).__name__}: {exc}"}


def one_run(
    client: httpx.Client,
    url: str,
    model: str,
    system: str,
    prompt: str,
    prompt_index: int,
    max_tokens: int,
    temperature: float,
) -> RunResult:
    """Stream one completion and time it."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        # Both vLLM and SGLang honour this and return a final usage chunk.
        "stream_options": {"include_usage": True},
    }

    ttft: float | None = None
    counted_deltas = 0
    usage_tokens: int | None = None

    start = time.perf_counter()
    with client.stream("POST", f"{url}/chat/completions", json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Prefer the server's own count when it sends one.
            if usage := chunk.get("usage"):
                if (completion := usage.get("completion_tokens")) is not None:
                    usage_tokens = completion

            for choice in chunk.get("choices", []):
                content = (choice.get("delta") or {}).get("content")
                if content:
                    if ttft is None:
                        ttft = time.perf_counter() - start
                    counted_deltas += 1
    e2e = time.perf_counter() - start

    if ttft is None:
        raise RuntimeError("no content tokens received — endpoint returned an empty stream")

    output_tokens = usage_tokens if usage_tokens is not None else counted_deltas

    # TPOT is undefined for a single-token output; report None rather than a lie.
    generation_s = e2e - ttft
    tpot_ms = (generation_s / (output_tokens - 1)) * 1000 if output_tokens > 1 else None
    tok_s = output_tokens / generation_s if generation_s > 0 else None

    return RunResult(
        prompt_index=prompt_index,
        ttft_ms=ttft * 1000,
        e2e_ms=e2e * 1000,
        output_tokens=output_tokens,
        tpot_ms=tpot_ms,
        output_tok_s=tok_s,
    )


def summarise(results: list[RunResult]) -> dict[str, object]:
    def stats(values: list[float]) -> dict[str, float | None]:
        clean = [v for v in values if v is not None]
        if not clean:
            return {"mean": None, "p50": None, "p95": None, "p99": None}
        return {
            "mean": round(sum(clean) / len(clean), 2),
            "p50": round(percentile(clean, 50), 2),
            "p95": round(percentile(clean, 95), 2),
            "p99": round(percentile(clean, 99), 2),
        }

    return {
        "ttft_ms": stats([r.ttft_ms for r in results]),
        "tpot_ms": stats([r.tpot_ms for r in results]),
        "e2e_ms": stats([r.e2e_ms for r in results]),
        "output_tok_s": stats([r.output_tok_s for r in results]),
        "output_tokens": stats([float(r.output_tokens) for r in results]),
    }


def print_table(engine: str, summary: dict[str, object], n: int) -> None:
    # ASCII only: the Windows console defaults to cp1252 and box-drawing
    # characters raise UnicodeEncodeError there. The JSON result file is
    # written as explicit UTF-8, so nothing is lost by keeping stdout plain.
    print()
    print(f"--- {engine} - {n} measured runs " + "-" * max(0, 40 - len(engine)))
    print(f"  {'metric':<16}{'mean':>10}{'p50':>10}{'p95':>10}{'p99':>10}")
    rows = [
        ("TTFT (ms)", "ttft_ms"),
        ("TPOT (ms)", "tpot_ms"),
        ("E2E (ms)", "e2e_ms"),
        ("output tok/s", "output_tok_s"),
        ("output tokens", "output_tokens"),
    ]
    for label, key in rows:
        s = summary[key]
        cells = "".join(
            f"{s[k]:>10.1f}" if s[k] is not None else f"{'n/a':>10}"
            for k in ("mean", "p50", "p95", "p99")
        )
        print(f"  {label:<16}{cells}")


def main() -> int:
    # Belt-and-braces for Windows: even with ASCII output above, a model name
    # or error string could carry non-cp1252 bytes. Never let formatting kill
    # a run whose measurements already succeeded.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Benchmark an OpenAI-compatible venue (TTFT/TPOT/throughput).",
    )
    parser.add_argument("--engine", default="vllm", help="label for the result file (vllm|sglang)")
    parser.add_argument(
        "--url",
        default=None,
        help="OpenAI-compatible base URL (default: the engine's host port - sglang 1020, vllm 1021)",
    )
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct-AWQ")
    parser.add_argument("--runs", type=int, default=20, help="measured runs (after warm-up)")
    parser.add_argument("--warmup", type=int, default=2, help="discarded warm-up runs")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--no-write", action="store_true", help="print only, do not write JSON")
    args = parser.parse_args()
    if args.url is None:
        # Each engine has its own host port (Makefile SGLANG_PORT / VLLM_PORT), so a
        # fixed default would benchmark whichever engine happens to own it.
        port = {"sglang": 1020}.get(args.engine, 1021)
        args.url = f"http://localhost:{port}/v1"

    if not PROMPTS_PATH.exists():
        print(f"prompt fixture missing: {PROMPTS_PATH}", file=sys.stderr)
        return 2

    fixture = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    prompts: list[str] = fixture["prompts"]
    system: str = fixture["system"]
    max_tokens: int = fixture["max_tokens"]
    temperature: float = fixture["temperature"]

    gpu_before = gpu_snapshot()
    print(f"engine:   {args.engine}")
    print(f"endpoint: {args.url}")
    print(f"model:    {args.model}")
    print(f"prompts:  {len(prompts)} (fixture v{fixture.get('version')})")
    print(f"runs:     {args.runs} measured + {args.warmup} warm-up")
    if "name" in gpu_before:
        print(f"gpu:      {gpu_before['name']} - {gpu_before['memory_free_mib']} MiB free")
    print()

    results: list[RunResult] = []
    failures = 0

    with httpx.Client(timeout=args.timeout) as client:
        try:
            client.get(f"{args.url}/models").raise_for_status()
        except Exception as exc:
            print(f"endpoint unreachable: {exc}", file=sys.stderr)
            return 1

        total = args.warmup + args.runs
        for i in range(total):
            is_warmup = i < args.warmup
            prompt_index = i % len(prompts)
            label = "warmup" if is_warmup else f"run {i - args.warmup + 1}/{args.runs}"
            try:
                result = one_run(
                    client,
                    args.url,
                    args.model,
                    system,
                    prompts[prompt_index],
                    prompt_index,
                    max_tokens,
                    temperature,
                )
            except KeyboardInterrupt:
                print("\ninterrupted", file=sys.stderr)
                return 1
            except Exception as exc:
                failures += 1
                print(f"  {label:<14} FAILED  {type(exc).__name__}: {exc}")
                continue

            if is_warmup:
                print(f"  {label:<14} discarded  (ttft {result.ttft_ms:.0f} ms)")
            else:
                results.append(result)
                tpot = f"{result.tpot_ms:.1f}" if result.tpot_ms is not None else "—"
                print(
                    f"  {label:<14} ttft {result.ttft_ms:>7.1f} ms   "
                    f"tpot {tpot:>6} ms   {result.output_tokens:>4} tok"
                )

    if not results:
        print("\nall measured runs failed", file=sys.stderr)
        return 1

    summary = summarise(results)
    print_table(args.engine, summary, len(results))
    if failures:
        print(f"\n  {failures} run(s) failed and were excluded")

    if args.no_write:
        return 0

    payload = {
        "engine": args.engine,
        "model": args.model,
        "endpoint": args.url,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runs_measured": len(results),
        "runs_warmup": args.warmup,
        "runs_failed": failures,
        "prompt_fixture_version": fixture.get("version"),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "gpu": gpu_before,
        "summary": summary,
        "runs": [asdict(r) for r in results],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"{args.engine}-{stamp}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nresults: {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
