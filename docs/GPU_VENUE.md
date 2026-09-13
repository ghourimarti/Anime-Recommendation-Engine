# Self-Hosted GPU Venue — vLLM vs SGLang

Measured evidence for the multi-venue serving decision (D4b / D12): can a
self-hosted open-weight model serve the simple end of this workload, which
engine, and at what latency?

**Answer: yes — both engines clear every latency NFR by 20–45×. They finish
within 2.6% of each other on total time, so the engine choice is made on
operational factors, not speed. Recommendation: vLLM.** Evidence below.

---

## 1. Hardware and model

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 3060, 12 GB, compute 8.6 |
| Driver | 591.86 |
| Host | Windows 11, Docker Desktop (WSL2 backend), 24 logical cores, 31 GB RAM |
| Model | `Qwen/Qwen2.5-7B-Instruct-AWQ` (4-bit AWQ, 5.2 GB on disk) |
| Engines | `vllm/vllm-openai:latest` · `lmsysorg/sglang:latest` |

AWQ 4-bit quantisation was chosen so a 7B model fits a 12 GB consumer card with
room for KV cache. An unquantised 7B (fp16, ~15 GB) does not fit at all.

**One engine at a time.** A 12 GB card holds exactly one 7B model — both engines
claim ~90% of VRAM. The launch scripts refuse to start alongside each other.
Both read the *same* weights volume, so switching engines downloads nothing.

---

## 2. Setup gotchas worth knowing

**vLLM — CUDA UVA allocation error.** The default model runner failed on this
driver/WSL2 combination. Workaround: `VLLM_USE_V2_MODEL_RUNNER=0`.

**vLLM — CLI drift.** This image's `vllm serve` takes the model as a
**positional argument** (`--model X` is deprecated and warns), and
**`--disable-log-requests` has been removed entirely** — passing it aborts
startup with `unrecognized arguments` before any model loading. Pin your image
digest if you depend on flag stability.

**vLLM — `--help` requires `--gpus all`.** vLLM infers device type while
*constructing* the argument parser, so `docker run --rm <image> --help` without
GPU access dies with `RuntimeError: Failed to infer device type`.

**SGLang — entrypoint is NVIDIA's passthrough wrapper**
(`/opt/nvidia/nvidia_entrypoint.sh`, no CMD), so the launch command is supplied
explicitly: `python3 -m sglang.launch_server`.

**SGLang — different flag names for the same concepts.** The parity mapping:

| concept | vLLM | SGLang |
|---|---|---|
| model | positional argument | `--model-path` |
| GPU memory budget | `--gpu-memory-utilization` | `--mem-fraction-static` |
| context window | `--max-model-len` | `--context-length` |

---

## 3. Methodology

Harness: `scripts/bench_venue.py`. Deliberately venue-agnostic — it targets any
OpenAI-compatible `/v1/chat/completions` endpoint and knows nothing about the
engine behind it, so both engines are measured by identical code against an
identical frozen prompt fixture. An engine-specific harness would void the
comparison.

| | |
|---|---|
| Prompts | `scripts/venue/prompts.json` v1 — 10 fixed anime-preference queries, 10–30 tokens |
| Generation | `max_tokens=256`, `temperature=0.0` (deterministic) |
| Runs | 20 measured, 2 warm-ups discarded |
| Concurrency | single-stream (latency, not throughput ceiling) |
| Memory budget | 0.90 both engines · context 4096 both engines |
| Prefix caching | **each engine's default** (SGLang RadixAttention on, vLLM APC on) |

Prefix caching is left at defaults deliberately. Disabling one engine's headline
feature to "be fair" would benchmark a crippled engine; defaults are what you
would actually deploy.

Metric definitions — these are easy to get subtly wrong:

- **TTFT** — request sent → first streamed token. Requires streaming.
- **TPOT** — `(e2e − ttft) / (output_tokens − 1)`. **Not** `total / tokens`,
  which double-counts prefill and makes every engine look slower than it is.
- **tok/s** — output tokens ÷ generation time (`e2e − ttft`), decode rate
  excluding prefill.

Warm-ups are discarded because the first request triggers CUDA graph capture and
cache warming; including it penalises whichever engine is measured first.

---

## 4. Results

### vLLM

```
  metric                mean       p50       p95       p99
  TTFT (ms)             42.4      38.2      54.4      93.5
  TPOT (ms)             14.8      14.8      14.9      14.9
  output tok/s          67.9      67.9      68.1      68.3
  output tokens        149.2     148.0     171.0     171.0
```

TPOT spread across all 20 runs: **14.8 → 14.9 ms**.

### SGLang

```
  metric                mean       p50       p95       p99
  TTFT (ms)             55.1      39.9     105.3     249.5
  TPOT (ms)             14.4      14.4      14.5      14.5
  output tok/s          69.8      69.8      69.9      70.1
  output tokens        143.4     135.0     170.0     170.0
```

TPOT spread across all 20 runs: **14.4 → 14.5 ms**.

### Against the project NFRs

| NFR | Target | vLLM | SGLang |
|---|---|---|---|
| TTFT p50 | < 800 ms | **38.2 ms** (21× under) | **39.9 ms** (20× under) |
| TTFT p95 | < 2 500 ms | **54.4 ms** (46× under) | **105.3 ms** (24× under) |
| Full response p95 | < 8 000 ms | **2 554 ms** (3.1× under) | **2 480 ms** (3.2× under) |

Both engines are far inside every budget. Latency is not the constraint here.

---

## 5. Head to head

Reproduce with `make venue-compare`. The script verifies condition parity first
and refuses to report a delta if any controlled variable drifted.

```
metric                  vLLM    SGLang    better    margin
TTFT p50                38.2      39.9      vLLM     1.04x
TTFT p95                54.4     105.3      vLLM     1.94x
TTFT p99                93.5     249.5      vLLM     2.67x
TPOT p50                14.8      14.4    SGLang     1.03x
TPOT p99                14.9      14.5    SGLang     1.03x
tok/s p50               67.9      69.8    SGLang     1.03x

length-normalised, 146 output tokens:
  vLLM     2203 ms
  SGLang   2145 ms          <- SGLang 2.6% faster overall
```

**Raw end-to-end latency is not comparable.** At temperature 0 the engines still
emit slightly different output lengths (149.2 vs 143.4 tokens mean), so E2E is
confounded by how much text each produced. The length-normalised figure is the
honest total-time comparison.

**The split:** SGLang decodes ~3% faster; vLLM's first-token latency is far more
consistent at the tail (2.67× better p99). For a 146-token response, prefill is
under 2% of total time — so SGLang's decode edge wins on paper by ~58 ms.

---

## 6. Recommendation: vLLM

**A 2.6% total-time difference is not a decision.** Both engines clear every NFR
by more than an order of magnitude, so speed does not discriminate. The decision
is made on operational cost:

| factor | vLLM | SGLang | matters because |
|---|---|---|---|
| Decode throughput | 67.9 tok/s | **69.8 tok/s** | ~58 ms per response — real but marginal |
| TTFT p99 | **93.5 ms** | 249.5 ms | first-token consistency is what a streaming UI exposes to users |
| Image size | **28.8 GB** | 52.2 GB | 23 GB on a disk-constrained box (S19 had to free 45 GB to start) |
| Cold load | **~130–205 s** | ~240 s | iteration speed during development |
| Ecosystem | **larger** | growing | more deployment references, more answered questions |
| CLI stability | drift observed | none observed | vLLM removed a flag between versions — pin digests either way |

vLLM wins on disk, cold start, tail consistency and ecosystem; SGLang wins a
2.8% decode margin. On this workload and this hardware, the operational factors
dominate.

### When this recommendation would flip

**SGLang's RadixAttention advantage does not show up in this benchmark.** Our
fixture is 10 *distinct* short prompts sharing only a system message — almost no
prefix reuse. RadixAttention pays off when many requests share long prefixes:
multi-turn conversations, agent loops, batch jobs over a long shared context.

**If the workload shifts that way, re-measure.** This is a workload-specific
recommendation, not a general claim that vLLM is the faster engine.

---

## 7. The finding: host contention dominates GPU headroom

The first vLLM run produced a **bimodal** TPOT distribution — 15 runs at ~18 ms
and 5 at ~52 ms, a 2.8× split. It was not prompt-dependent: the same prompt
returned 57.7 ms on one run and 17.8 ms on another.

The initial hypothesis was VRAM paging — the card showed only 417 MiB free and
Windows WDDM pages desktop allocations under CUDA pressure. **That hypothesis
was wrong.** The clean re-run had *less* free VRAM (1 547 MiB) and was perfectly
stable. The variable that actually changed was 27 competing containers (another
project's observability stack) being stopped.

| metric | contended host | quiet host | delta |
|---|---|---|---|
| TTFT p50 | 43.5 ms | 38.2 ms | 1.1× |
| TPOT p50 | 18.2 ms | 14.8 ms | 1.2× |
| **TTFT p99** | **3 489.7 ms** | **93.5 ms** | **37.3×** |
| **TPOT p99** | **58.6 ms** | **14.9 ms** | **3.9×** |

**Medians barely moved; tails collapsed.** The decode loop needs host CPU for
scheduling and detokenisation, so a saturated host stalls it intermittently —
exactly the non-prompt-dependent bimodal signature observed.

Two practical consequences:

1. **`nvidia-smi` "free memory" did not predict anything** on this WDDM host.
   CUDA evicts pageable desktop allocations on demand, so a low free figure is
   not a blocker and a high one is not a guarantee. The SGLang run started with
   243 MiB free and performed fine.
2. **Benchmark tail latency is a host-quietness measurement** until proven
   otherwise. Any inference benchmark reporting p99 without stating host load is
   reporting noise.

---

## 8. Reproducing

```bash
make venue-status                        # GPU + running venue containers
make venue-up-vllm                       # or: make venue-up-sglang
make venue-bench                         # or: make venue-bench ENGINE=sglang
make venue-compare                       # parity-checked head to head
make venue-down                          # stop, free VRAM
```

**Condition lock** — any comparison run must match:

```
host quiet (unrelated container stacks stopped)
memory budget 0.90, context length 4096
prompt fixture v1, max_tokens 256, temperature 0.0
20 measured runs, 2 warm-ups discarded, single-stream
prefix caching at each engine's default
```

Each result file records these in metadata, so `compare.py` verifies parity
rather than assuming it — and voids the comparison if anything drifted.

Raw per-run results: `Documents/docs/venue-bench/` (gitignored — machine-specific).

---

## 9. Scope and honest limits

- **Single-stream only.** This measures latency for one user, not the throughput
  ceiling under concurrency. Concurrent load belongs with the k6 work against
  the real API path.
- **Consumer hardware.** An RTX 3060 on a Windows desktop is not a production
  serving environment. These numbers establish that the *pattern* works and give
  D4b a real input; they are not a claim about production capacity.
- **No HA.** One card, one host, residential uplink. A self-hosted venue in
  production needs a GPU node group — a separate cost decision.
- **N=20 per engine.** Enough to separate a 2.7× tail difference; not enough to
  resolve the 3% decode gap with confidence. Treat "SGLang is 2.8% faster" as
  directional, not established.
- **Prefix-reuse workloads untested.** See §6 — the recommendation flips if the
  workload gains long shared contexts.

---

## 10. Status

| Item | State |
|---|---|
| vLLM baseline | ✅ measured |
| SGLang baseline | ✅ measured |
| Head-to-head | ✅ parity-verified |
| Engine recommendation | ✅ **vLLM**, on operational factors (§6) |
| Venue integration | ⏳ S21, behind `LLM_VENUE_ROUTING_ENABLED=false` |
