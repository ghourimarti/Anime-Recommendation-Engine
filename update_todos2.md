# Update Todos 2 — detailed tracker (Track L, findings, gates, evidence)

> **Clean phase summary lives in `update_todos.md`** (phases 0–10 + Track D, one line per item). This file keeps everything else: Track L, findings, decision gates, measurements. Split made 2026-09-14 on request.

> Living tracker. Long-form plan with rationale: `Documents/docs/transformation-plan.md`
> Decision record: `docs/DECISION_LOG.md`

**Legend:** ✅ complete · 🔄 in progress · ⏸️ blocked · ⏳ pending
**Last updated:** 2026-09-14 — **Track L complete (10/10)**: `make up` / `up-sglang` / `up-vllm` / `down` all verified live; SGLang 0.70 and vLLM 0.90 at context 8192 on ports 1020 / 1021 · Phase 6 3/12 (G6–G9=A). Gates: G1=B PAT auth · G2=B lockfile · G3=A layered values · G4=A chart=app version · G5=C cd.yml untouched

---

## Phase topology

```
Phase 0 ──► Phase 1 ──► ... ──► Phase 5  (development complete)
                                    │
                                    ▼
                    PHASE 6 — Release Packaging
                    "build once, deploy many"
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
        PHASE 7                PHASE 8                PHASE 9
    Local & kind            Real managed K8s          AWS EKS
        ($0)                    (metered)          (portability)
              └─────────────────────┼─────────────────────┘
                                    ▼
                           PHASE 10 — Portfolio
```

Phases 7/8/9 are parallel in dependency (each needs only Phase 6). Recommended
execution order is still 7 → 8 → 9 (free → metered → expensive).

---

## PHASE 0 — Recon ✅ 3 / 3

- ✅ P0.1 Read repo, map stack and data flow
- ✅ P0.2 Baseline report — present / partial / absent layer map
- ✅ P0.3 Package mapping → Package 1 (Production-grade RAG)

## PHASE 1 — Requirements & NFRs ✅ 3 / 3

- ✅ P1.1 Functional scope — multi-tenant anime-recommendation SaaS
- ✅ P1.2 NFRs @ 100k MAU — TTFT p50 800 ms / p95 2.5 s, 50 RPS sustained / 200 peak, 99.5% SLO, <$0.005/req
- ✅ P1.3 Out-of-scope list — 15 explicit exclusions

## PHASE 2 — Decision Log ✅ 5 / 5

- ✅ P2.1 Decision dependency graph
- ✅ P2.2 22 decisions (D1 Postgres → D22 monorepo)
- ✅ P2.3 At-a-glance summary table
- ✅ P2.4 Revisions — D5 (`text-embedding-3-small` 1536-dim), D6 (LangChain v1 factories), D11 (SQS + EKS workers)
- ✅ P2.5 **D4b added + D12 amended** — multi-venue serving, written during S20.8

## PHASE 3 — Transformation Plan ✅ 4 / 4

- ✅ P3.1 18 risk-front-loaded steps
- ✅ P3.2 v1.1 — deployment phases split, vendor-portability principle
- ✅ P3.3 v1.2 — S19/S20 GPU venue spikes as separate steps; S21 venue integration
- ✅ P3.4 v1.3 — Phase 6 Release Packaging inserted; phases renumbered 7/8/9/10, made parallel

---

## PHASE 4 — Execution ✅ 21 / 21

- ✅ **S1** Repo skeleton + workspace config [D22]
- ✅ **S2** Data ingestion + Postgres + pgvector + OpenAI embeddings [D1, D2, D5]
- ✅ **S3** Hybrid retrieval + cross-encoder reranker + MMR [D3]
- ✅ **S4** Eval golden set + RAGAS harness + IR metrics + A/B runner [D19]
- ✅ **S5** Tiered LLM client + structured grounded recs + LangChain v1 chains [D4, D6]
- ✅ **S6** FastAPI service — recommend / stream / feedback / history + health [D7]
- ✅ **S7** 3-layer Redis cache — embedding / response / semantic [D10]
- ✅ **S8** Circuit breakers + fallback chains + kill switch [D21]
- ✅ **S9** Clerk JWT auth + multi-tenant scoping + ACL-at-retrieval [D9, D18]
- ✅ **S10** Per-user daily quota + token-budget guard + cost meter [D20]
- ✅ **S11** structlog + OTel + Langfuse + PII redaction [D13, D18]
- ✅ **S12** Next.js + Clerk → streaming UX → cover art → app shell + ⌘K palette [D8]
- ✅ **S13** Docker multi-stage + compose e2e parity (incl. LocalStack) [D15]
- ✅ **S14** SQS workers + KEDA ScaledObjects + DLQ + idempotency [D11]
- ✅ **S15** Terraform modules — vpc, eks, rds, elasticache, s3, sqs, iam, secrets, ecr, monitoring [D14, D15]
- ✅ **S16** Helm chart + ArgoCD ApplicationSet + Argo Rollouts canary + ESO [D15, D16, D17]
- ✅ **S17** GitHub Actions CI + RAGAS eval gate + Trivy + tag-triggered ECR push [D16, D19]
- ✅ **S18** k6 load suite + tuning + portfolio docs

### ✅ S19 — GPU venue spike: vLLM [D12, D4b] — COMPLETE (risk to app ~0%, none realised)

- ✅ S19.0 Hardware recon — RTX 3060 12 GB, compute 8.6, nvidia runtime present
- ✅ S19.1 Disk cleanup — 45.55 GB freed, C: 47→148 GB
- ✅ S19.2 Docker → GPU passthrough verified (`nvidia-smi` in container)
- ✅ S19.3 Model decision — Qwen2.5-7B-AWQ; Llama-3.1 HF token ready
- ✅ S19.4 vLLM image pull — 9.11 GB download / 30.8 GB on disk
- ✅ S19.5a UVA blocker solved — `VLLM_USE_V2_MODEL_RUNNER=0`
- ✅ S19.5b HF token passthrough fixed
- ✅ S19.5c Weight download — **COMPLETE**, verified 2026-09-12: 5.2 GB, both shards finalized, all 9 snapshot symlinks resolved
- ✅ S19.6 Measure TTFT / TPOT / tok-s
  - ✅ S19.6a Harness written + verified — `venue/prompts.json`, `venue/up_vllm.sh`, `bench_venue.py`, `venue/down_venue.sh`, Makefile targets
  - ✅ S19.6b Harness bugs found + fixed by running it — vLLM CLI drift (`--disable-log-requests` removed, model now positional); cp1252 console crash on box-drawing chars
  - ✅ S19.6c Clean measurement — **BASELINE ESTABLISHED**. TTFT p50 38.2 / p99 93.5 ms · TPOT 14.8 ms (zero variance, 14.8–14.9 across all 20) · **67.9 tok/s** · E2E p95 2554 ms
  - ✅ S19.6d Root cause of contamination identified — **host contention from 27 competing containers**, NOT VRAM paging. Stopping the other project's stack collapsed TPOT p99 3.9× (58.6→14.9 ms) and TTFT p99 37× (3490→93.5 ms). GPU had only 1547 MiB free during the clean run and performed perfectly — "free VRAM" was a red herring.
- ✅ S19.7 `docs/GPU_VENUE.md` written (tracked, portfolio-facing) · teardown reclaimed 9686 MiB VRAM · orphaned partials deleted: volume 8.2G → 5.2G, **3.0 GB reclaimed**, 9/9 symlinks verified intact
- ✅ S19.8 Protocol A/B/C artifacts + commit prep

### ✅ S20 — GPU venue spike: SGLang [D12, D4b] — COMPLETE (risk to app ~0%, none realised)

- ✅ S20.1 SGLang image pull — **already present** (`lmsysorg/sglang:latest`, 52.2 GB)
- ✅ S20.2 Cache reuse confirmed — SGLang image sets no HF env overrides, defaults to `/root/.cache/huggingface`; same `vllm-hf-cache` volume mounts unchanged, **zero re-download**. CLI parity mapped: `--mem-fraction-static`↔`--gpu-memory-utilization`, `--context-length`↔`--max-model-len`
- ✅ S20.3 SGLang server up — `scripts/venue/up_sglang.sh` + `make venue-up-sglang`; loaded ~240 s on port 8001 with parity flags (`--mem-fraction-static 0.90` ↔ vLLM gpu-util, `--context-length 4096` ↔ max-model-len). Preflight refuses to start alongside vLLM and warns when the host is busy (S19 finding)
- ✅ S20.4 `.env` venue toggle — `LLM_VENUE` / `LLM_VENUE_URL` / `LLM_VENUE_MODEL` + `LLM_VENUE_ROUTING_ENABLED=false` (S21 dark-ship gate) documented in `.env.example`
- ✅ S20.5 Measured with the identical harness + fixture — TTFT p50 39.9 / p95 105.3 / p99 249.5 ms · TPOT 14.4 ms · **69.8 tok/s** · E2E p50 1985 ms. Conditions matched (2 containers, quiet host)
- ✅ S20.6 A/B comparison — `scripts/venue/compare.py` + `make venue-compare`, parity-checked (6/6 controlled vars match, voids itself on drift). **Split decision: vLLM wins TTFT tails (p99 2.67×), SGLang wins decode (+2.8% tok/s). Length-normalised: SGLang 2145 ms vs vLLM 2203 ms for 146 tok — a 2.6% gap.** Both clear every NFR by 20–45×, so speed is not the deciding factor
- ✅ S20.7 `docs/GPU_VENUE.md` extended — both engines, parity mapping table, head-to-head, **recommendation (vLLM) with the flip condition**, host-contention finding, scope limits
- ✅ S20.8 **D4b added + D12 amended** in `docs/DECISION_LOG.md` — new Decision 4b (multi-venue serving) with measured evidence table + engine flip condition; D12 amended to separate its *cost* argument from the *capability* claim measurement refuted; at-a-glance row + 2 revision-history entries added
- ✅ S20.9 Protocol A/B/C artifacts + commit prep — 6/6 verification green, clean teardown (11472 MiB free), both images intact

### ✅ S21 — Multi-venue serving integration [D4, D4b, D12] — COMPLETE 11 / 11 — routing LIVE

> Mandatory guard: `LLM_VENUE_ROUTING_ENABLED=false` by default. Ships dark.

- ✅ S21.0 Cost-meter zero-rate for the venue model — self-hosted tokens have no *marginal* cost, merged as a default in `get_pricing()` so flipping the flag can't die with `UnknownModelError` on the hot path; explicit `LLM_PRICING` still wins (21 tests pass)
- ✅ S21.1 `VenueClient` — `ChatOpenAI` with `base_url` at the local endpoint. Both engines are OpenAI-compatible, so this is ~20 lines, not a new client hierarchy
- ✅ S21.2 Venue config — `venue_enabled/url/model/timeout/confidence_threshold()` read lazily from env (matches the existing lazy-config precedent)
- ✅ S21.3 Wired — `build_default_llm_client()` flag branch (venue imported INSIDE the function; module-level would be circular since venue.py imports from llm_client.py) + `RETRIEVAL_CONFIDENCE` published by both `recommend()` and `astream()` via `_top_rerank_confidence()`. **Flag-off identity PROVEN**: inner is exactly `TieredLLMClient`, unchanged. **284/284 tests pass, 0 regressions.** ruff + mypy clean
- ✅ S21.4a **Confidence distribution MEASURED** (111 golden queries) — `scripts/venue/measure_confidence.py`. clear −0.49 > edge −3.22 > vague −4.84 > adversarial −11.25 (medians), monotonic as hypothesised. **VERDICT: SEPARATES**
- ✅ S21.4b **Threshold derived from data: 1.0** — lowest value where 0% of vague queries misroute, costing only 3 pts of clear coverage vs 0.0. Routes 44% clear / 18% edge / 0% vague / **0% adversarial**. Adversarial is 0% at every threshold to −6.0 (max −9.70) — structural, not tuned
- ✅ S21.4c Router — `should_use_venue()` **fails safe**: `None` confidence (reranker timeout → hybrid fallback) routes to hosted, never the weakest model
- ✅ S21.5 Circuit breaker — `build_venue_client()` reuses the existing `ResilientLLMClient` + `AsyncCircuitBreaker(name="venue")`
- ✅ S21.6 Fall-through chain — `VenueRoutedClient` wraps (not modifies) `TieredLLMClient`; handles failure, refusal, and empty-result separately; stream falls through only before the first token
- ✅ S21.7 Per-venue observability — `record_venue_decision()` counter (hosted / venue_served / venue_fallback_error / venue_fallback_empty) with the alert condition in its description; `record_retrieval_confidence()` histogram so live drift from the golden-set distribution is visible; `langfuse_tags=["venue","self-hosted"]` via a new optional `metadata` param on `_LangChainClient` (None for every pre-existing client, so their config is unchanged). All 5 routing paths behaviourally verified — **every path still returns an answer**
- ✅ S21.8 Eval regression — **PASS: no detectable quality cost to routing 26% of traffic to the 7B**
  - ✅ S21.8a Harness selection — **`make eval` is retrieval-only** (QueryRetriever + IR metrics, never calls an LLM), so flag-off vs flag-on would be identical and reporting it as "no regression" would be a false assurance. `make eval-refusal` runs the full service but its adversarial queries score ≤ −9.70, far below the 1.0 threshold, so they never reach the venue — necessary, not sufficient. Purpose-built A/B written instead
  - ✅ S21.8b **Control pass added after the first design failed** — v1 compared one off-pass to one on-pass and "FAILED" on a query with confidence −9.0 that routing never touched. LLM output is non-deterministic even at temperature 0. v2 runs OFF / OFF-control / ON so provider noise is measured, not attributed to the feature
  - ✅ S21.8c **Noise floor measured: 35%** (7/20 recommendation sets change between two *identical* passes). The single-baseline design would have blamed all of it on routing
  - ✅ S21.8d Verdict given a ~2 sd Poisson margin — a bare `effect > noise` test fails on 4-vs-3 at n=12, which is evidence of nothing
  - ✅ S21.8e Full 111-query × 3-pass run — **PASS**. 29/111 (26%) venue-eligible, matching the predicted 26% exactly. Noise floor (off vs off): 41 set-changes, 34 below-threshold, 7 refusal flips, 17 fewer-item. Routing effect (off vs on): 40 / 23 / 7 / 16 — **at or slightly below noise on every metric**. The n=20 "fewer grounded items" concern (2 vs 5) did NOT survive at n=111 (17 vs 16) — it was sampling noise, caught by the significance margin
- ✅ S21.9 Tests — `packages/core/tests/test_venue.py`, **19 tests**: threshold boundary (inclusive at 1.0), fail-safe on None, dark-ship default, below/above-threshold routing, failure + empty fall-through, **refusal honoured not second-guessed**, streaming fall-through before first token, **flag-off composition identity**, flag-on wrapping, zero-rate cost + explicit-config override. **303/303 suite passes** (was 284)
- ✅ S21.10 **Flag flipped ON + verified live** — `LLM_VENUE_ROUTING_ENABLED=true` in `.env`. End-to-end through the real HTTP API: high-confidence (+5.395) → **vLLM delta 1**, returned "Fullmetal Alchemist"; low-confidence (−10.434) → **vLLM delta 0**, hosted served. Revert = set the flag back to `false`, no redeploy
  - ✅ S21.10a **Bug found + fixed during live verification** — OTel histograms reject negative values, and rerank scores are raw logits (−11 to +7), so `anime.retrieval.confidence` was silently recording NOTHING for most queries. Now records `sigmoid(logit)`: non-negative, bounded, monotonic (percentiles preserved), interpretable as probability. Routing still compares the RAW logit, so the decision is never mediated by the transform
  - ✅ S21.10b Finding — **the signal is phrasing-sensitive**. "relaxing slice of life comedy about quirky high school girls" = +4.083 but "gentle comedy about cute schoolgirls doing everyday things together" = −3.248. Near-identical semantics, 7.3 points apart. The threshold is defensible on the measured distribution but individual routing decisions are brittle to wording — the confidence histogram is how drift gets caught
  - ✅ S21.10c **Container-networking bug found + fixed** (surfaced by a "how do I run this?" question). `anime-vllm` sat on the default bridge, not the compose network, while `.env` carries `localhost:8001` — so a CONTAINERISED api (`make app`) could never reach the venue and would **silently fall through to hosted while the GPU sat idle**. Fixed the way this repo already fixes it for Langfuse: both venue scripts join `anime-recommender_default` and claim the shared alias `anime-venue`; compose overrides `LLM_VENUE_URL` for api **and** worker. The alias is shared by both engines, so app config stays engine-agnostic

---

## PHASE 5 — Hardening ✅ 5 / 5

*3 batches / 36 files / 9 commits / +10 RTBF tests / 241 tests pass*

- ✅ P5.1 Secrets · dependency · license audit
- ✅ P5.2 Load test — k6 suite (smoke / 50rps / stream 30rps / peak 200rps / ramp-to-knee)
- ✅ P5.3 Chaos drills — `kill_llm.sh` / `kill_pg.sh` / `net_partition.sh` / `restore.sh`
- ✅ P5.4 Backup / restore drill — idempotent restore
- ✅ P5.5 Runbooks · alerts · cost thresholds · log retention · RTBF
  - ✅ P5.5.1 Runbooks — provider-outage, cost-spike, db-down, eval-regression
  - ✅ P5.5.2 Alerting routing — conditional Slack stack
  - ✅ P5.5.3 Cost-alert threshold verification
  - ✅ P5.5.4 Log retention policy — class-based via TF var
  - ✅ P5.5.5 RTBF — Clerk-first, idempotent audit row

---

## PHASE 6 — Release Packaging 🔄 4 / 12

> "Build once, deploy many." One immutable signed artifact set, consumed unchanged by Phases 7/8/9.
>
> **Gates locked:** G1=B PAT registry auth (cosign signing stays keyless — separate OIDC token) ·
> G2=B digests in a lockfile · G3=A layered values · G4=A chart version = app version ·
> **G5=C `cd.yml` left untouched** — two pipelines publish independently, so "same digest
> everywhere" is FALSE until resolved. **Recorded as a Phase 9 blocker for P9.5's portability proof.**
>
> **Phase 9 blockers found during P6.7** (deliberately not fixed — G5=C): ① two builds → two digests (above) · ② `cd.yml` pushes `anime-api` (flat) but the chart pulls `anime-recommender/api` — ①② documented in `values-aws.yaml` · ③ `cd.yml` bump-helm regex needs `tag: vX.Y.Z` in `values-prod.yaml`, which has always had `tag: ""` → the first release's bump job exits "No tag patterns matched"
>
> **Release workflow decisions approved 2026-09-14:** R1=A tag `v*.*.*` + manual dry-run · R2=B web reads site URL + Clerk publishable key at RUNTIME (one web image for every environment) · R3=A digest lockfile as Release asset + auto-PR to `release/images.lock` · R4=A third-party actions pinned by commit SHA · R5=A linux/amd64 only · R6=A ghcr app images + chart public (MinIO mirror stays private). Build order: R2 web runtime config → `release.yml` + `docs/RELEASE.md` + `make package` + render-verify in CI → local checks → your push, dry-run, tag. GitHub secrets verified present by name: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `GHCR_PAT`. Local tools: helm 4.1.4, actionlint 1.7.12, buildx 0.36; syft / trivy / cosign not installed (they run in CI)
>
> **R2 implemented 2026-09-14 (static checks pass; live two-container proof pending):** new `apps/web/src/lib/runtime-config.ts` (`siteUrl()` / `configuredSiteUrl()` / `clerkPublishableKey()`, runtime names first, `NEXT_PUBLIC_*` fallback for `pnpm dev`) + 5 unit tests; `layout.tsx` renders per request (`dynamic = "force-dynamic"`, `generateMetadata()`), passes `publishableKey` to `ClerkProvider`; `middleware.ts` passes it via the per-request options callback and keeps the req.url fallback when no site URL is configured; web Dockerfile build ARGs removed; compose web gets runtime `SITE_URL` / `CLERK_PUBLISHABLE_KEY` mapped from the existing `.env` names (no `.env` change); Helm `web.yaml` + `web.siteUrl` / `web.clerkPublishableKey` values (local: http://localhost:3000; empty derives https://<ingress.host>); ci.yml web image build args removed; `.env.example` comment. **Checks:** compose config shows runtime env + only the billing build arg; `make render-verify` PASS (12/12, 3 negative controls); web typecheck 0, lint 0, tests 28/28.
>
> **Release workflow implemented 2026-09-14 (P6.2–P6.6, P6.8; written and linted, NOT yet run on GitHub):** `.github/workflows/release.yml` · tag `v*.*.*` or manual dry run (publish only on a plain vX.Y.Z tag) · per image: build once (amd64, base from `base-images.lock`) → Trivy v0.74.0 gate (fixable HIGH/CRITICAL) → syft v1.51.1 SPDX SBOM → `docker push` of the scanned image to ghcr + Docker Hub, fail if digests differ → cosign v3.1.3 keyless sign both refs + SBOM attestation → `cosign verify` as a consumer · chart: kubeconform v0.7.0 (sha256-verified) + render-verify → `helm package` version = app version → push `oci://ghcr.io/ghourimarti/charts` → sign + verify · record: `release/images.lock` + `release/values-images.yaml`, Release assets, auto-PR · all 10 third-party actions pinned to commit SHAs. `docs/RELEASE.md` (one-time setup incl. making ghcr packages public by hand, dry run, verify, deploy by digest, caveats). `make package` (local bundle, nothing pushed). `ci.yml` new `chart` job (render-verify) required by `CI OK`. **Checks:** `actionlint` clean on release.yml + ci.yml; `make -n package` shows render-verify → 3 pinned-base builds → chart package. **Unproven until run on GitHub:** cosign v3 signing/attest/verify, Docker Hub digest equality, the PR step. Next: your push, a dry run, then tag v0.1.0
>
> **GitHub push 2026-09-14 (commit 0db4d9e, 44 files; none of JUNK/, root package.json / pnpm-lock.yaml, .env):** CI run 34828924992 — **new `chart` job PASSED**; `python`, `web`, `images` x3, `supply chain`, `CI OK` failed, the **same 6 jobs that failed on the 13 Sep run** (pre-existing). Causes: images x3 — `aquasecurity/trivy-action@0.28.0` no longer resolves; python — ruff SIM102 + UP017 x2 on old lines of `scripts/bench_venue.py`; supply chain — secret scan flags the dummy Clerk key `pk_test_ZXhh...` in `ci.yml` history; web — under investigation. Eval Gate failed: `OPENAI_API_KEY` repo secret not set (user side; failing on every run since mid-August)
>
> **CI fixes F1–F5 approved 2026-09-14 (applied locally, not pushed yet):** F2 `trivy-action` pinned to commit `ed142fd…` (v0.36.0) in `ci.yml` · F3 ruff UP017 ×2 + SIM102 fixed in `scripts/bench_venue.py`; CI's `ruff format --check` also flagged 4 files, re-wrapped with no logic change (`packages/core/tests/test_otel.py`, `scripts/venue/compare.py`, `scripts/venue/eval_routing.py`, `scripts/venue/measure_confidence.py`) · F4 web job cause found: setup-node's `cache: pnpm` post step looked for a store path `pnpm install` in `apps/web` never wrote → replaced by `pnpm store path` + `actions/cache@55cc834…` (v6.1.0) · F5 secret scan allowlists the base64 body of the dummy CI Clerk key (checked: dummy key → placeholder, a realistic-looking key → still flagged) · F1 → see L.16. **Local checks:** `ruff check` + `ruff format --check` clean (157 files), `mypy packages apps` clean (85 files), `actionlint ci.yml` clean, unit tests 334 passed. Still user side: `OPENAI_API_KEY` secret for Eval Gate
>
> **Push verified 2026-09-16 (CI run 35065397285) — all four CI fixes worked:** `web` **PASS** (F4: the pnpm store cache), `chart` PASS, secret scan clean (F5), ruff + format clean (F3), and `trivy-action` now resolves (F2). **Three deeper failures were hiding behind them, and every one of them also blocks `release.yml`, which shares the Trivy policy:**
> - **C.1 python tests: 307 passed, 27 errors** — `PricingConfigError: LLM_PRICING is empty`. The `apps/api` tests read pricing from the developer's local `.env`, which CI does not have. Pre-existing; masked until ruff stopped failing first. Fix belongs in the api test fixtures, not in the workflow env.
> - **C.2 supply chain: 9 HIGH** — `aiohttp` 3.14.1 (PYSEC-2026-3545/3546/3547), `cryptography` 49.0.0 (PYSEC-2026-3552), `transformers` 5.9.0 (PYSEC-2026-3929). Separately the **pnpm audit could not run** ("pnpm not on PATH") and correctly failed closed — that job needs pnpm installed.
> - **C.3 images x3 Trivy: the same three packages**, all marked *fixed* upstream (aiohttp CVE-2026-69244, cryptography CVE-2026-69247, transformers CVE-2026-9856). One dependency bump closes C.2 and C.3 together. The base image also carries an unfixed openssl CRITICAL, which the gate correctly ignores (it gates on FIXABLE findings).
> - **C.4 (found 2026-09-16 by pre-flighting the gate locally, before the release could fail on it):** ran Trivy **v0.74.0 — the exact version release.yml pins — with the exact policy (`--severity HIGH,CRITICAL --ignore-unfixed`) against the images `make package` builds. Result: **the release WOULD have failed its image gate**: worker 20 findings (16 HIGH, 4 CRITICAL), web 13, api scan timed out at the default budget (2.8 GB image; it needed `--timeout 20m`). Every finding was an OS package in the base image with a fix already published: `libgnutls30` 3.7.9-2+deb12u5 -> u7, `openssl`/`libssl3` 3.0.18 -> 3.0.19/3.0.20, `libpcre2-8-0`, `libcap2` on Debian; `libcrypto3`/`libssl3` 3.5.7-r0 -> 3.5.8-r0 on Alpine.
> - **`make base-images-refresh` did NOT fix it** — the lock was already at the newest published digests. The distros had shipped the fixes; the upstream `uv` and `node` images had not been rebuilt with them. So the remedy `docs/RELEASE.md` predicted ("bump base-images.lock and tag again") did not apply, and waiting on upstream would have blocked the release indefinitely.
> - **Fix (your call, 2026-09-16): patch at build + drop npm.** `apt-get upgrade` in the api and worker runtime stages, `apk upgrade` in the web runtime stage, and **removal of the bundled npm CLI** from the web runtime — nothing there uses it (pnpm builds, `node server.js` runs) and it vendored its own tree (`brace-expansion`, `ip-address`, `pacote`), which was most of that image's remaining findings. **Trade-off recorded honestly:** the image is no longer a pure function of the pinned base digest, because the apt/apk snapshot moves; what ships stays auditable through `release/images.lock` plus the SBOM attestation. **Verified: api PASS, web PASS, worker PASS — the release image gate would now pass on all three.**
>
> **C.1-C.3 FIXED 2026-09-16 (local; awaiting your push):**
> - **C.1** — `apps/api/tests/conftest.py` now injects `TEST_PRICING` into `CostMeter` instead of reading the ambient `LLM_PRICING`. `CostMeter(pricing=...)` already existed for exactly this ("tests inject their own table"), so the fix uses the designed seam rather than adding env to the workflow. A test reading live rates would also start failing the day a provider changes one — noise, not signal. **Verified by reproducing CI first:** with pricing unavailable the suite went **33 passed + 27 errors -> 60 passed**.
> - **C.3 / Python half of C.2** — `uv lock --upgrade-package` x3: aiohttp 3.14.1 -> **3.14.3**, cryptography 49.0.0 -> **50.0.1**, transformers 5.9.0 -> **5.17.0**. Python audit clean, suite **344 passed**, mypy + ruff clean. transformers was a 5.9 -> 5.17 jump under sentence-transformers, so the cross-encoder was loaded for real and scored a known pair correctly (Cowboy Bebop above Naruto) rather than trusting mocked unit tests.
> - **C.2 Node half — a finding the fix itself exposed.** Adding pnpm to the audit job (so `deps.py`'s Node half can run at all) surfaced **22 HIGH advisories CI had never seen**, because the job had been failing closed before reaching them. Resolved in four rounds, each revealing the next layer: `next` 15.5.25 + `sharp` 0.35.4 (22 -> 13 HIGH), then `postcss` 8.5.28 + `js-yaml` 4.3.2 (13 -> 8), then `browserslist` 4.29.0 + `brace-expansion` (8 -> **0**). **Audit now PASSES** (MEDIUM vitest + LOW remain, non-blocking by the gate's own policy). Overrides follow the file's existing documented convention; `js-yaml` was first written `>=4.3.2`, which silently resolved to **5.4.2** (a major jump) and was corrected to `^4.3.2`, and `brace-expansion` uses pnpm's version-scoped override syntax so neither of its two copies crosses a major.
> - **Verification gap, stated plainly:** the web lockfile was resolved **metadata-only** (`--lockfile-only`) because the network was dropping tarball downloads, so `node_modules` still holds the old versions locally. The `postcss` override forces Next's internally pinned 8.4.31 upward, which needs a real `pnpm build` to confirm. Until that runs, the Node half is proven at the ADVISORY level, not the BUILD level.
> - **Environmental, not ours:** during this work three registries (ghcr.io, docker.io, npmjs.org) were dropping or stalling connections from this host - a user `make up` died on `TLS handshake timeout` fetching a base-image token, pnpm hit repeated `ECONNRESET`, and a plain `registry.npmjs.org/next` GET took **25 s** twice. Measured, not assumed. Worth doing later: `make up` resolves base images by TAG (a registry round trip every build) while `make package` already uses the digests in `base-images.lock` - pinning the local path too would remove this failure mode.

- ✅ P6.1 Reproducible builds — **`base-images.lock`** at repo root, shell-sourceable, pins `uv` + `node` by sha256 digest. All 3 Dockerfiles annotated that the lock is authoritative and the tag default is an unpinned fallback. `scripts/release/refresh_base_images.sh` + `make base-images-check|refresh`
  - ✅ P6.1a **Bug found by running it under make** — `docker` inside the `while read` loop consumed the loop's stdin, so it processed one entry then died. Works interactively (TTY), fails under make/CI — exactly where the gate runs. Fixed with `< /dev/null`; verified under TTY, make and piped stdin
- ⏳ P6.2 Dual registry setup
  - ⏳ P6.2.1 `ghcr.io` — deployment source of truth; **PAT auth per G1=B** (note: `GITHUB_TOKEN` + `packages: write` would need no stored credential)
  - ⏳ P6.2.2 Docker Hub — public showcase mirror only; never a cluster pull source
- ⏳ P6.3 Tagging — `:<git-sha>` immutable + `:vX.Y.Z` semver; `:latest` local-only
- ⏳ P6.4 SBOM (syft) + vulnerability scan (trivy) gating the push
- ⏳ P6.5 **Cosign keyless signing** (Sigstore/Fulcio/Rekor via GitHub OIDC) + verification policy
- ⏳ P6.6 Helm chart → OCI artifact on `oci://ghcr.io/ghourimarti/charts`, signed, version-pinned
- ✅ P6.7 Values matrix — **vendor-neutral `values.yaml`** (ghcr.io registry, `tag: ""` → `appVersion`) + `values-local` / `values-doks` / `values-aws`; layering base → vendor → env. Toggles: `rollout.enabled` (Deployment fallback sharing **one** pod template, `anime.api.podTemplate`) · `keda.enabled` + `keda.triggerMetadata` · `networkPolicy.ingressFrom` · `required()` on ESO store and `sqsQueueUrlBase`. **Characterization diff** (parsed YAML, old vs new aws × base/dev/staging/prod): only the intended changes
  - ✅ P6.7a **Bug:** prod rendered `…/api:` (empty tag → trailing colon). `helm` exits 0 and kubeconform accepts it; it fails only at kubelet pull. Fixed: tag falls back to `appVersion`, empty result fails the render
  - ✅ P6.7b **Dead config:** `api.canary.steps` was ignored — the template hardcoded an identical copy. Now rendered; `--set api.canary.steps[0].setWeight=99` probe proves it
  - ✅ P6.7c **NetworkPolicy wrong for EKS:** admitted the `ingress-nginx` namespace, but ALB IP-mode traffic comes from VPC ENIs — dropped with VPC CNI enforcement on, a silent no-op with it off. `values-aws` admits VPC CIDR `10.0.0.0/16`
  - ✅ P6.7d **Regression caught before commit:** the ArgoCD ApplicationSet layered only `values-<env>.yaml` (relying on the old AWS-shaped base) → all 3 Applications would fail to render. `valueFiles: [values-aws.yaml, values-<env>.yaml]`; proven identical to the gate render, old list proven failing
  - ✅ P6.7e Docs: chart README (layering + toggles-by-vendor table), root README deploy block, PR template checkbox
  - Left OPEN for Phase 8, disabled rather than guessed in `values-doks`: secret backend (P8.6) · SQS reachability + KEDA auth without IRSA
- ✅ P6.8 `make package` — full release bundle + `RELEASE.md`; also wires `make render-verify` into CI. **Verified live 2026-09-16:** `make package VERSION=0.1.0-rc1` exit 0 in 91 s — render-verify PASS (12/12 vendor x env + 3 negative controls), 3 images built on the `base-images.lock` bases (`anime-recommender/{api,web,worker}:0.1.0-rc1`), chart packaged to `dist/anime-recommender-0.1.0-rc1.tgz`. **G4 proven from the packaged artifact:** `helm show chart` gives version = appVersion = 0.1.0-rc1, and the aws overlay renders `…/anime-recommender/api:0.1.0-rc1` (tag empty -> appVersion); values-local deliberately pins `:local` for kind. `dist/` gitignored; `docs/RELEASE.md` 5.2 KB / 9 sections. Nothing pushed, scanned or signed — that is `release.yml` only. **Checked while verifying:** the worker image's layers were 44 h old because `apps/worker/Dockerfile` copies only core + ingestion + worker (no `packages/retrieval`), so the F1 change cannot affect it; the api image does contain the fix
- ✅ P6.9 Render-verify — `scripts/release/render_verify.sh` + **`make render-verify`**: 12/12 vendor × env renders · `kubeconform -strict` **offline** against pinned K8s v1.31.0 schemas (`yannh` @ `970cc70`, = EKS module version) + CRD catalog (`datreeio` @ `ad3b08c`) · contract: local renders emit no Rollout/AnalysisTemplate/ScaledObject/ExternalSecret · **3 negative controls** (unknown field rejected *for that field* · missing schema is an error not a skip · forced Rollout in local detected) · cold 7s / warm 5s · `helm lint` clean ×3 vendors
  - ✅ P6.9a **Found:** `kubeconform … | tail` exits 0 on invalid manifests (`$?` is tail's) → `pipefail`
  - ✅ P6.9b **Found:** downloading schemas during validation made the gate flaky — 2–3 of 12 renders failed on raw.githubusercontent 503s with **0 invalid manifests**; kubeconform probes the K8s location first for CRDs and a 503 there is fatal → fetch each schema once (curl retry/backoff), validate offline
  - ✅ P6.9c **Found:** the negative control could "pass" on a download error (any non-zero exit) → must be rejected for the corrupted field
  - ✅ P6.9d **Found:** kubeconform's default Kubernetes version is `master` → pinned to 1.31.0
- ⏳ P6.10 Consumption proof — pull from registry, `cosign verify`, deploy to kind

---

## PHASE 7 — Local & kind validation 🔄 2 / 6

> Cost $0. Answers: "are my manifests correct?"

- ✅ P7.1 Docker images — api / web / worker, multi-stage, non-root, healthchecks, Trivy-clean
- ✅ P7.2 `docker compose` full-stack cold-start e2e smoke + backup drill
  - ✅ P7.2.1 `scripts/deploy/smoke_local.sh` — hybrid auth coverage
  - ✅ P7.2.2 `deploy/stage1-local-docker.md`
  - ✅ P7.2.3 Makefile — `deploy-stage1`, `deploy-stage1-smoke`
  - ✅ P7.2.4 Acceptance run — cold start → migrate → ingest → smoke → k6 → backup drill → cleanup
  - ⏳ P7.2.5 Re-verify with registry-pulled images (post-Phase-6)
- 🔄 P7.3 kind cluster created; Helm chart installs green
  - ✅ P7.3.1 `values-local.yaml` — ESO off, Rollout off, Ingress off, `IfNotPresent` — **delivered early by P6.7** (also KEDA + NetworkPolicy off, empty registry for `kind load`)
  - ⏳ P7.3.2 `scripts/deploy/up_local_k8s.sh` — idempotent stand-up
  - ⏳ P7.3.3 `scripts/deploy/down_local_k8s.sh` — teardown (+ `--soft`)
  - ⏳ P7.3.4 `scripts/deploy/smoke_k8s.sh` — via `kubectl port-forward`
  - ⏳ P7.3.5 `deploy/stage2-local-k8s.md`
  - ⏳ P7.3.6 Makefile — `k8s-render`, `k8s-up`, `k8s-down`, `deploy-stage2`
  - ✅ P7.3.7 `helm template | kubeconform -strict` clean — **delivered early by P6.9**: `make render-verify` covers local × 4 envs, including the no-CRDs contract
- ⏳ P7.4 Probes, HPA, ConfigMap/Secret wiring, in-cluster DNS verified
- ⏳ P7.5 In-cluster failure drills — pod kill, rollout restart, node drain
- ⏳ P7.6 `terraform plan` reviewed (no apply)

**Open gates:** #1 kind · #2 plain K8s Secrets · #3 plain Deployment · #4 hand-rolled PG/Redis · #5 backup drill included → recommended `A/A/A/C/A`

---

## PHASE 8 — Real managed Kubernetes ⏳ 0 / 12

> Metered. DOKS first, vendor-portable by design.

- ⏳ P8.1 Vendor selection + cost model committed to repo
- ⏳ P8.2 Cluster provisioned via Terraform (never click-ops)
- ⏳ P8.3 `imagePullSecret` for ghcr.io — images pulled, not rebuilt
- ⏳ P8.4 Data tier — managed Postgres + Redis (or in-cluster for portability)
- ⏳ P8.5 ingress-nginx + cert-manager + TLS + DNS
- ⏳ P8.6 Secrets management — DO has no Secrets Manager → Sealed Secrets / SOPS / Vault
- ⏳ P8.7 App tier via `helm install … -f values-doks.yaml`; venue config per D4b
- ⏳ P8.8 Observability live — Prometheus, Grafana, alerts firing
- ⏳ P8.9 Load test against the real cluster — HPA actually scaling
- ⏳ P8.10 Chaos drills against the real cluster — node/pod failure
- ⏳ P8.11 Real cost measurement — $ per 1k queries
- ⏳ P8.12 Teardown runbook + `terraform destroy` verified — no orphaned LBs / volumes

---

## PHASE 9 — AWS EKS ⏳ 0 / 9

> Portability proof + the AWS-depth gap from the skill audit.

- ⏳ P9.1 AWS account + GPU-instance quota approved (Track D)
- ⏳ P9.2 Terraform — VPC + EKS + managed node groups
- ⏳ P9.3 IRSA — IAM Roles for Service Accounts, least privilege
- ⏳ P9.4 RDS (with PITR) + ElastiCache + SQS + Secrets Manager + ESO
- ⏳ P9.5 **Same chart + same digests via `values-aws.yaml` — diff must be config-only**
- ⏳ P9.6 GPU node group for a real self-hosted venue (`g4dn`/`g5` spot) — cost decision
- ⏳ P9.7 ArgoCD bootstrap + staging namespace + canary + rollback rehearsal
- ⏳ P9.8 Cost comparison — DOKS vs EKS, measured
- ⏳ P9.9 Portability findings written up

---

## PHASE 10 — Portfolio ⏳ 0 / 6

- ⏳ P10.1 Architecture diagram
- ⏳ P10.2 README rewrite
- ⏳ P10.3 Before/after metrics story — naive RAG → hybrid+rerank+MMR; API-only → multi-venue
- ⏳ P10.4 Findings writeup — every measurement that refuted an assumption
- ⏳ P10.5 Demo video / screenshots
- ⏳ P10.6 Interview talking points + consolidated senior-vs-junior table

---

## TRACK L — Local stack lifecycle (Makefile) 🔄 15 / 16

> Requested 2026-09-13. Every lifecycle command is built from base targets; only base targets call `docker compose`.
> **Gates:** M1=B hard rename, no aliases · M2=B `make up` stops any venue (frees the GPU) ·
> M3=B targets depend on the tier they need · M4=A live-verify up → up-sglang → up-vllm → down; `downv` / `upv` dry-run only
>
> **Measured before design** (throwaway compose project): `down <services>` leaves other tiers running ·
> `down -v <services>` deletes only that tier's volumes · `vllm-hf-cache` has no compose label, so no `downv` touches it ·
> a venue attached to the network makes a full `down` exit 0 but **leave the network behind** ·
> `.env` routing=true reaches the containers unless make passes the value explicitly

- ✅ L.1 Base compose targets — `up-data` (`--wait` until healthy) / `up-app` / `up-obs`, `down-*`, `downv-data` / `downv-obs`, `net-down`; `DC_*` variables removed. Dry-run step order verified
- ✅ L.2 Venue base targets — `venue-down-vllm` / `venue-down-sglang` / `venue-down`; `venue-up-vllm` depends on `venue-down-sglang` and vice versa; `venue-bench ENGINE=…` starts that engine first
- ✅ L.3 Mode targets — `up` (stops any venue, M2=B) · `up-vllm` · `up-sglang` + `make llm-status` (`scripts/venue/llm_status.sh`: routing flag, engine, network, **api → venue reachability from inside the container**). Dry-run verified; `make up` composite proven live (L.9a); `make up-sglang` brought every tier up with routing on and SGLang serves (`llm-status` → api → venue 200 afterwards), but the command exited 2 on the readiness wait (L.9g); repeated on 2026-09-14 with the new flags: exit 2 at the 900 s wait, SGLang serving 3 min later with `llm-status` SELF-HOSTED sglang; **2026-09-14 07:00 at 0.70 / 8192 / 1800 s: `make up-sglang` exit 0 in 458 s** (tiers 30 s, SGLang engine 390 s), `llm-status` SELF-HOSTED sglang; **`make up-vllm` exit 0 in 311 s** (stopped SGLang first, vLLM serving 226 s after start), `llm-status` SELF-HOSTED vllm — all three modes proven live
  - ✅ L.3a **Pitfall proven before use:** `up-vllm: up` would silently run API-only — make applies a prerequisite's own target variable over its caller's (scratch Makefile, GNU Make 4.4.1)
- ✅ L.4 Combined targets — `down`, `downv`, `upv`, `deploy-stage1` (API mode; wipes only data volumes, as before), `ps` = `ps-stack` + `venue-status`. No compose call outside the base targets
- ✅ L.5 Routing reaches the containers — compose interpolates `${VENUE_ROUTING:-false}` for api + worker. `docker compose config` with `.env` holding `true`: unset → false · false → false · true → true
  - ✅ L.5a **Bug avoided:** interpolating `${LLM_VENUE_ROUTING_ENABLED}` reads `.env` too — `.env` would have silently picked the mode for every command. A name `.env` does not define keeps the choice with the make target
- ✅ L.6 Venue scripts — an already-running venue gets attached to the app network; SGLang container port 30000 → 8000. `bash -n` clean; **proven live** (L.9c: attach control + api → SGLang 200, old port 30000 refused)
  - ✅ L.6a **Bug found by reading:** SGLang listened on 30000 inside its container while compose calls `anime-venue:8000` — a containerised api could never reach SGLang and silently fell back to the hosted LLM
- ✅ L.7 Dependents (M3=B) — `up-data`: ingest, retrieve, eval, eval-gate, eval-refusal, recommend, db-migrate, db-shell, dev-api, worker, sqs-init, backup-*, rtbf · `up-app`: chaos-llm/pg/net, deploy-stage1-smoke · `up-obs`: lf-models · `venue-up-$(ENGINE)`: venue-bench. **Deliberately none** on dev-web and load-* (port 1005 is served by the container OR a host api; auto-starting one collides with the other). CI calls uv directly, never make
- ✅ L.8 Hard rename (M1=B) — `db` / `app` / `obs` / `obs-up` / `obs-down` / `dev` removed (now "No rule to make target"); 31 edits across 9 files: README, 3 compose headers, root compose, `.env.example` (+ note that containers ignore its routing value), `measure_confidence.py`, both venue scripts
- ✅ L.9 Verification — live up → up-sglang → up-vllm → down (llm-status, containers, network, volumes, images at each step) · `make -n downv` / `make -n upv` ✅ dry-run order verified · **Complete 2026-09-14:** the full M4 sequence ran live — `make up` (13 Sep), then `make up-sglang` 458 s, `make up-vllm` 311 s and `make down` 43 s (14 Sep), all exit 0
  - ✅ L.9a **`make up` live, all three tiers:** 19 containers — 16 running, 3 one-shots exited 0 (migrate, sqs-init, minio-create-bucket) · `llm-status` → API-based, rc 0 (routing `false` inside the api while `.env` says `true`) · HTTP 200: api /health + /ready, web, Grafana, Prometheus, OTel metrics, MinIO · Langfuse 200 (`3.225.4`) once its cold start finished (~4 min) · first run pulled the 4 pinned obs images
  - ✅ L.9b **Observability tier unblocked (O2):** cached `minio/minio` mirrored to a **private** `ghcr.io/ghourimarti/minio:RELEASE.2025-09-07T16-13-09Z` (pushed by you with `scripts/release/mirror_image.sh`). Verified here: package visibility `private` · registry digest `sha256:a1a8bd4a…` = the pin for both `minio` and `minio-create-bucket` in `docker-compose.obs.yml` · `compose config --images` resolves no Docker Hub MinIO image. Original blocker: `minio/mc` + `minio/minio` no longer pull from Docker Hub (pre-existing, not caused by Track L)
  - ✅ L.9c Venue path on the app tier (needs no obs) — base targets, live:
    - ✅ `make up-app VENUE_ROUTING=true`, then `llm-status` correctly WARNs "routing on but no venue" (an unplanned negative control)
    - ✅ **vLLM end to end:** `venue-up-vllm` stopped SGLang first (VRAM free 4545 → 10206 MiB), started vLLM on the app network; `llm-status` → api → venue **200**, "SELF-HOSTED vllm"
    - ✅ **Attach control:** detached SGLang → `llm-status` "on app network: no" + WARN; rerun `venue-up-sglang` → "already running" + **"attached"** → "on app network: yes"
    - ✅ **SGLang port fix proven:** after an extra wait, `llm-status` → api → venue **200**, "SELF-HOSTED sglang"; direct probe from inside the api: `anime-venue:8000` → 200, `anime-venue:30000` → connection refused
    - ✅ Nothing deleted: both engine images and the `vllm-hf-cache` weights volume intact
  - ✅ L.9d **`make down` live:** venue stopped first (VRAM free 232 → 11547 MiB), 0 anime containers, 0 venue containers, network removed. Kept: 7 project volumes, `vllm-hf-cache`, all 5 images. The 7 kind nodes untouched · **Re-verified 2026-09-14 with the new ports and flags:** `make down` exit 0 in 43 s, vLLM stopped first (VRAM free 636 → 10,318 MiB), 0 anime and 0 venue containers, network removed, 0 orphan warnings; kept 7 project volumes, `vllm-hf-cache` and all 6 images
  - ✅ L.9e **Venue readiness wait:** both venue scripts hardcode 300 s; on this host (17 running containers) SGLang became ready at ~363 s, twice. `make up-sglang` therefore fails although SGLang does come up. **Decision: W1**, implemented — `--wait SECS` in both venue scripts (non-integer rejected with exit 2 before any Docker call), `VENUE_WAIT_SECS ?= 600` passed through by `venue-up-*` (override per run), help + usage updated. Static checks pass. **Your live `make up-sglang` timed out at 600 s twice**; on the 2026-09-14 run SGLang's own startup total was 631 s, missing the wait by ~31 s (see L.9g) · **W applied:** `VENUE_WAIT_SECS ?= 900` · **Live 2026-09-14: still timed out at 900 s** (`make up-sglang` exit 2, 1,761 s including the image rebuild): SGLang container start 06:30:42 UTC, weights alone took 401 s, and the wait ended during CUDA-graph capture · **W2 applied (2026-09-14):** `VENUE_WAIT_SECS ?= 1800`, P5's ENGINE_WAIT; SGLang starts measured here: 363 / 631 / 1,118 s · **W2 confirmed live:** `make up-sglang` exit 0 in 458 s (SGLang engine startup 390 s); 1800 s also covers the worst start measured here (1,118 s)
  - ✅ L.9f **Finding resolved — the Langfuse worker's `Socket timeout … 30000ms` errors are idle-queue noise, not failures (not caused by Track L).** Source verified: the message is defined in `ioredis@5.10.1` (`built/Redis.js`), the Redis client behind Langfuse's BullMQ queues — not in `@clickhouse/client`. (My first attribution to ClickHouse was unchecked and wrong.) Jobs are not failing: two snapshots 30 s apart show `failed=0` on every queue, nothing waiting or active, `trace-upsert` completed 1 — while 24 errors were logged; 30 of 97 Redis clients sit in blocking reads, i.e. idle workers timing out their 30 s wait. Separately, ClickHouse's first-boot saturation (1856% CPU with 26 containers running) settled to ~2% CPU, host HTTP `SELECT 1` at 61—80 ms
  - ✅ L.9g **Finding — SGLang slow start traced to `--mem-fraction-static 0.90` (resolved at 0.70 — see the end of this item).** Found by comparing with P5-Medical-Chatbot, where both engines work on this same card: P5's Makefile documents that SGLang's fraction is of TOTAL VRAM and ignores what the Windows desktop already holds, and uses **0.50** (P1 uses 0.90). P1's own log agrees: `Memory pool end. avail mem=0.37 GB`, then prefill CUDA-graph capture at `avail_mem=0.00 GB`, first graph 4 m 55 s. Same card, stopped `tp-sglang` container at 0.55 vs ours at 0.90: load weights 12 s vs 167 s · KV-cache allocation 0.4 s vs 80 s · free after pool 4.87 GB vs 0.37 GB · prefill capture 206 s vs 322 s · **total 229 s vs 631 s**. Not confirmed: spill into shared system memory (Windows shared-GPU counter 125 MB while serving). Even at 0.55 the prefill capture costs ~206 s on this machine. Consequence for S20: the "0.90 ↔ 0.90" parity with vLLM was nominal, not equivalent memory — **D applied:** correction note in `docs/GPU_VENUE.md` §2, the §3 memory row, the §8 condition lock, and the overstated "compare.py verifies parity" line (it checks 6 recorded conditions, none of them memory, context length or host load). The 13-Sep 37-min start is likely the same starvation plus a cold disk (unproven) · **Live run at 0.50 (container start 06:30:42 UTC):** weight load 400.75 s (0.90 run: 167 s) while C:, Docker's disk, sat idle at 0.2–0.5 MB/s and the VM held 13.6 GB of page cache — so the slow load is NOT the C: drive (cause unknown; the busy disk was E:, a 2 TB HDD Docker does not use, at 414%). **New concern — KV cache only 1,618 tokens at 0.50** (0.90: 83,721; `tp-sglang` at 0.55: 11,881), smaller than one request at `--context-length 4096` and than the app's `.env.example` budget (3,000 input + 1,200 output). Free VRAM after the pool was 5.57 GB, far more than CUDA-graph capture used on `tp-sglang` (~1.9 GB), so a fraction between 0.50 and 0.90 likely serves both. **G is not counted as fixed until a real-size request is served by SGLang** · **Result at 0.50:** serving at 06:49:20 UTC, **18 min 38 s** after container start (0.90 run: 631 s). Engine timings: load_weight 400.75 s (0.90: 166.56), kv_cache_allocation 0.56 s (0.90: 79.97), prefill CUDA graph 396.21 s with 4.48 GB free (0.90: 321.91 s at 0.00 GB). **So memory starvation did NOT cause the slow start** — with ample free VRAM, weight load and graph capture were still slow; that part of the G diagnosis was wrong, and the startup cause remains unknown. Limits at 0.50: max_total_num_tokens 1,618, max_req_input_len 1,612. Direct requests: 76- and 1,126-token prompts served (HTTP 200); 3,326 + 1,200 tokens rejected by the 4,096 context limit, not by the KV cache (see L.9i). KV-limit isolation test and a real app request running · **KV test:** a real app request ("anime like Fullmetal Alchemist Brotherhood…") was served by SGLang — 907-token prompt, **56% of the 1,618-token KV cache** for one request. Direct prompts of 1,676 and 2,476 tokens were rejected: HTTP 400 "Input length exceeds the maximum allowed length (1612 tokens)". **Verdict: 0.50 is not acceptable here** — it did not speed up startup, and it rejects any prompt over 1,612 tokens although the app allows 3,000, sending those silently to Groq / OpenAI. Fraction decision pending · **F1 applied:** `SGLANG_MEM_FRACTION ?= 0.70` and script default 0.70 (estimated ~42k-token KV cache and ~3 GB free — to be measured). The Makefile comment, script header and the `GPU_VENUE.md` correction note were rewritten so they no longer blame slow starts on memory · **Live at 0.70 (run start 07:00:30 UTC):** tiers already up, so SGLang started after 30 s (no image rebuild); weight load 62 s; **KV cache 42,669 tokens** (estimate ~42k confirmed); free after the pool 2.17 GB (estimate ~3 GB — lower than estimated); CUDA-graph capture in progress. App healthy meanwhile: api /health + /ready, web and Langfuse 200, 16 containers running, none unhealthy; `llm-status` correctly WARNs that requests fall back to Groq / OpenAI while SGLang loads · **Verified at 0.70:** serving after 390 s engine startup (weights 62 s, prefill CUDA graph 316 s); max_total_num_tokens 42,669, max_req_input_len 8,186; 1.22 GB free after capture and ~0.4 GB free card-wide with the desktop (OOM risk if desktop apps grow). Direct prompts of 76 / 1,126 / 3,326 tokens all HTTP 200; a real app query was served by SGLang (886-token prompt, 2% of the KV cache). Slow-start cause still unknown (engine starts measured 390–1,118 s) · **Independent confirmation:** Prometheus `anime_llm_venue_decisions_total{decision="venue_served"}` went 0→1 at 06:51:30 and 1→2 at 07:09:30, and Langfuse generations at 06:51:00 and 07:08:36 were `Qwen/Qwen2.5-7B-Instruct-AWQ` (ChatOpenAI) — SGLang really served both app queries
  - ✅ L.9h **Defect (Track L): compose warns "Found orphan containers" on every per-tier call** — each base target loads only its own tier's compose files, so the other tiers' containers look like orphans. Harmless today, but anyone adding `--remove-orphans` would delete the other tiers. **H applied:** `export COMPOSE_IGNORE_ORPHANS := true`; verified that make passes it to compose; **confirmed live:** 0 orphan warnings across all 3 tier compose calls (data, app, observability) of `make up-sglang` on 2026-09-14; the previous run printed one on every tier call
  - ✅ L.9i **Finding — app token budget exceeds the venue context (pre-existing, S21 config):** `LLM_MAX_INPUT_TOKENS=3000` + `LLM_MAX_OUTPUT_TOKENS=1200` = 4,200 > `--context-length 4096`. SGLang rejected a 3,326 + 1,200-token request with HTTP 400 "exceeds the model's maximum context length". A rejected venue call does not raise in the app — it silently falls back to Groq / OpenAI. vLLM runs the same 4,096 limit (not yet tested there). One real app prompt measured at 907 tokens (SGLang prefill log); the size range across queries is not yet measured · **C1 applied:** `VENUE_CONTEXT_LEN ?= 8192`, passed to both engines (vLLM `--max-len`, SGLang `--context-len`); script defaults 8192; the `GPU_VENUE.md` condition lock notes S19/S20 ran at 4096. Dry runs verified; live check pending · **SGLang verified at 8192:** the 3,326 + 1,200-token request rejected at 4096 now returns HTTP 200 (prompt 3,326, finish=stop); **vLLM verified at 8192:** KV cache 52,688 tokens (6.43× concurrency at 8,192), 76 / 1,126 / 3,326-token prompts all HTTP 200, **CORRECTED 2026-09-14:** the "real app query served by vLLM" claim was wrong — vLLM received a request at 07:15, but Langfuse recorded the answer from Groq `openai/gpt-oss-20b` and Prometheus captured no routing decision for it; unverified, see L.15
- ✅ L.10 **Separate host ports per engine (requested 2026-09-14):** SGLang → **1020**, vLLM → **1021**. Verified free: no Windows listener, no Windows excluded port range, no Docker binding. Container port stays 8000, so the app's `anime-venue:8000` path is unchanged. Touches every hardcoded 8001: Makefile (`VENUE_PORT`, `VENUE_URL`, help), both venue scripts, `bench_venue.py` default, `venue.py` default, `.env.example` (and your `.env` for a host-run api). **P applied:** `SGLANG_PORT ?= 1020` / `VLLM_PORT ?= 1021` in the Makefile, both venue script defaults, `bench_venue.py` default URL follows `--engine`, `venue.py` default 1021, `.env.example`; your `.env` already had 1021. **Static checks pass:** dry runs show `--port 1020 --mem-frac 0.50 --wait 900` and `--port 1021 --wait 900`, command-line overrides work, help updated, 0 real `8001` references left, 19/19 venue tests pass, ruff clean on changed lines (3 older findings on untouched `bench_venue.py` lines 143/329/342 left as is). **Live:** SGLang container publishes 1020 → 8000 (IPv4 + IPv6) with `--port 8000 --mem-fraction-static 0.50 --context-length 4096`; the old 8001 no longer answers. **SGLang verified live:** 1020 → HTTP 200; `llm-status` SELF-HOSTED sglang with api → venue 200; 8001 closed. vLLM on 1021 pending `make up-vllm` · SGLang re-verified at 0.70 / 8192: 1020 → 8000, `llm-status` api → venue 200 · **vLLM verified live:** container publishes 1021 → 8000, 1021 → HTTP 200, 1020 closed after the switch, `llm-status` SELF-HOSTED vllm with api → venue 200. Free VRAM with vLLM running: ~0.36 GB card-wide (same OOM caution as SGLang)
- ✅ L.11 **Live startup progress for venue engines (requested 2026-09-14):** replace the silent dots with phases parsed from the engine's own log (config, weights, KV cache, CUDA-graph capture k/42, serving) with elapsed time; warn when the log goes quiet; fail fast on fatal errors (Traceback, CUDA out of memory) instead of waiting the full 1800 s. **Approved 2026-09-14; implementing** (`scripts/venue/_progress.sh`) · **Implemented 2026-09-14:** `scripts/venue/_progress.sh` (`watch_startup`) sourced by both venue scripts in place of the dots. Phases from the engine log with elapsed time and detail (weights time, KV tokens, CUDA-graph k/N), 60 s heartbeat, silence WARNING after 300 s, fail-fast on container exit and CUDA OOM, tracebacks shown but not fatal; here-strings instead of `| grep -q` (pipefail/SIGPIPE). **Offline test with fake docker/curl/sleep/date: 5/5 cases pass** (SGLang + vLLM happy paths rc 0; stall warn + timeout, OOM, container exit rc 1). Live check pending in L.15 · **Verified live 2026-09-14 (vLLM start at 08:40 UTC, during the slow-VM period):** phases with elapsed time (config parsed 1:45, loading weights 2:51), 60 s heartbeats and the silence WARNING at 304 s all appeared during a real 17-min start, so a slow start was visibly progressing instead of silent dots. Fail-fast paths (OOM, container exit) proven offline only
- ✅ L.12 **Langfuse auto-provisioned (requested 2026-09-14):** `make up` / `make up-obs` must come up with the Langfuse user, org, project and API keys already created, and the api tracing queries immediately · no sign-up, no org/project creation, no copying keys into `.env`. **Diagnosed 2026-09-14 — already working:** the obs compose seeds Langfuse via `LANGFUSE_INIT_*` on first boot of an empty DB, pinned to `.env`'s keys. Langfuse DB: user `admin@anime.local`, org `anime-local`, project `anime-recommender` (all created 2026-07-26), project API key **matches** `.env` `LANGFUSE_PUBLIC_KEY`. Public API with `.env` keys: HTTP 200, 81 traces, latest a real `POST /v1/recommend` at 08:05 UTC; 0 export failures after Langfuse finished starting (the earlier 5 s timeouts were during its cold start). Remaining: the Langfuse UI has no anonymous mode, so one login per browser with the seeded account; show it in `make service_ls` (L.13); traces go to Langfuse twice (SDK direct + collector) — check for duplicates · **Closed 2026-09-14 (user):** nothing to build; the seeded login is shown by `make service_ls` (L.13)
- ✅ L.13 **Service directory (requested 2026-09-14):** (1) `make up` / `upv` / `up-vllm` / `up-sglang` end by printing every service URL **without credentials**; (2) new `make service_ls` lists every component · app, both Postgres DBs, Redis, LocalStack, ClickHouse, MinIO, Langfuse, Grafana, Prometheus, OTel, vLLM / SGLang · with live status, URLs and full connection details incl. credentials (for pgAdmin etc.), read from `.env` at run time. **Approved 2026-09-14** (design: `urls` without credentials, live status; `scripts/service_ls.sh` with credentials from `.env`) · **Implemented 2026-09-14:** `scripts/service_ls.sh` (one script, two modes); Makefile `urls` -> `--urls`, new `service_ls`, `upv` prints URLs after ingest, 11 `@echo` lines made ASCII (`·`/`—` showed as `Â·` in the user's terminal). **Verified on the live stack:** `make urls` lists app, setup jobs, LLM mode, engines, databases, storage and observability with live status and no credentials; `make service_ls` adds pgAdmin fields, connection URLs, MinIO / Langfuse / Grafana logins and Langfuse API keys (checked with output masked). Fixed after the run: name column 26 → 30 chars
- ✅ L.14 **Defect found 2026-09-14 — `make up` can fail while the api is still loading:** a diagnostic `make up` exited 2 after 272 s (08:16:28 UTC). api container started 08:15:33, server process 08:15:49, **application ready 08:17:18 (105 s)** — the reranker model load dominates. The api image healthcheck allows only start_period 20 s + 3 × 15 s ≈ 65 s, so it is marked unhealthy ≈08:16:38 while `web` waits on `api: service_healthy` — strongly consistent with compose aborting `make up`, NOT proven (that run's output was discarded). The api recovered on its own (healthy, /ready 200). Also: `migrate` sat 155 s silent before alembic's first line and shows `unhealthy` because it inherits the api image healthcheck without serving /health.  · **Fix applied (approved 2026-09-14):** app compose api healthcheck override — same probe, `start_period: 180s`, `start_interval: 5s`; `migrate` healthcheck disabled. `docker compose config` verified; live check in L.15 (`make up-vllm` recreates the api) · **Live check 2026-09-14 (make up-vllm, routing false→true recreated the api):** the api runs with `start_period=3m0s start_interval=5s`, `migrate` has no healthcheck, compose printed 0 "dependency failed / unhealthy" lines and the app tier came up. Honest limit: this api was ready in **10 s** (08:41:08→08:41:18), so the 105 s slow-start race was not reproduced; the fix is verified in effect, not under the slow case
- ⏳ L.15 **Correction + retest: does vLLM really serve routed app queries?** The 07:15 UTC verification query reached vLLM (access log) but Langfuse recorded a Groq `gpt-oss-20b` generation and no Qwen one, and no routing decision was captured (the api was stopped ~90 s later). Retest after the L.14 fix: `make up-vllm`, one high-confidence app query, then require BOTH a Prometheus `venue_served` increment and a Langfuse Qwen generation. Related: the user's 08:05 query used Groq with no routing decision recorded — routing was most likely off, so the 08:12 diagnostic `make up` most likely did not stop an engine in use (not provable: Docker keeps no event history on this machine) · **Approved 2026-09-14** · **Retest run 2026-09-14 08:40 UTC:** `make up-vllm` brought the app tier up with routing on; the L.11 progress display worked live (config parsed 1:45, loading weights 2:51, 60 s heartbeats, silence WARN at 304 s). **vLLM then crawled through weight loading:** stuck-looking at `Loading safetensors checkpoint shards: 0/2` for 13+ min (07:11 run: 2.25 s). Diagnosis: EngineCore state R at 99.5% of one core; voluntary context switches flat over 2 s (pure CPU, no I/O or GPU calls); two py-spy dumps 10 s apart on different tensors (`load_row_parallel_weight`, then `load_merged_column_weight`) — progressing, ~300x slower. Ruled out: disk (C: 0.2 MB/s), VM memory (14 GB available, 11 GB cache), GPU spill into system RAM (Windows shared GPU memory 198 MB), host CPU contention (host idle). Cause unknown. py-spy was pip-installed inside the throwaway vLLM container for the dumps. The background run was stopped before its 1800 s deadline so no queries hit a half-loaded engine; vLLM keeps loading and the routing queries rerun once it serves · **Diagnosis continued 2026-09-14:** Windows power plan is *Power saver* (Ryzen 9 7900X at ~72% of max frequency; suggestive, not proven). CPU speed normal right now (Python loop 0.25–0.34 s host vs 0.55–0.59 s in the Docker VM, ~2x = usual VM overhead). **GPU path healthy:** staged test inside the vLLM container — CUDA init 1.1 s, host→GPU 64 MB 0.008 s, GPU→host 0.068 s. **Correction:** flat voluntary context switches do not rule out GPU calls (non-blocking ioctls do not switch). A first 512 MB test was cut by a 150 s timeout without output (it only printed at the end) and left a stray process in the vLLM container, competing with the loader; nonvoluntary switches rose 1,355→3,547. vLLM was still moving through tensors 24 min in. **Action:** stopped the watcher, restarting vLLM (`make venue-down-vllm` + `make venue-up-vllm`, container only) to tell a transient stall from an environmental one; routing queries run once it serves · **Restart result 2026-09-14:** vLLM served at 09:30:17 but `Loading weights took 1026.79 s` (07:11 run: 2.25 s) — the slowness is persistent since ~07:21, not transient. `llm-status` SELF-HOSTED vllm. **All 3 routing queries returned HTTP 500 from the api** (L.16), vLLM received 0 requests — routing still unproven · **ROOT CAUSE FOUND 2026-09-16 (two live runs, api rebuilt with the F1 fix, routing on, vLLM serving):** run 1 — 3 app queries all HTTP 200, all answered by Groq, decisions `hosted` 1→4, **0 confidence samples in the histogram**; run 2 — warmed the cross-encoder first (warm-up query's reranker RAN, 1 sample recorded), then 3 queries about anime that ARE in the corpus (Cowboy Bebop / Monster / Naruto, all non-refusals with items) — **3 reranker timeouts in the api log**, decisions `hosted` 4→8, venue_served 0, vLLM requests 0, Qwen generations 0. **So this is not a routing bug:** `_top_rerank_confidence` returns None whenever the cross-encoder misses `RERANK_TIMEOUT=2.0s`, and `should_use_venue(None)` fails safe to the hosted chain by design. The model IS resident (a 1-candidate warm-up scores inside 2 s); scoring ~20 candidates on this VM does not. Also found: the corpus is the older MAL top-269 (Cowboy Bebop, Monster, Naruto, Fullmetal Alchemist 2003) — **no Death Note, no Attack on Titan**, which is why run 1's queries came back as honest refusals. **Options, none applied yet (needs your call):** (a) raise `RERANK_TIMEOUT` for local runs and re-prove; (b) measure real rerank duration for 20 candidates and set the budget from data; (c) accept that the venue is unprovable on this host and prove routing on GPU-backed k8s later. Visible only because the metric exists — this is exactly the silent degradation Track O's dashboards must surface
- ✅ L.16 **Defect found 2026-09-14 — every `/v1/recommend` returns HTTP 500:** `sqlalchemy.exc.PendingRollbackError: Can't reconnect until invalid transaction is rolled back`, from the first request after the api was recreated at 08:41 (first 500 at 09:32:54; a fresh query at ~09:40 still fails). `/health` and `/ready` return 200. No earlier error in the api log. Diagnosing the session handling (`anime_core/db/engine.py`, `anime_api/dependencies.py`) · **Root cause (from the request log, 2026-09-14):** 09:40:02 request start → 09:40:08 Postgres "canceling statement due to user request" on the pgvector query (`ORDER BY embedding <=> $2`) → api "dense (pgvector) retrieval failed; falling back to sparse-only" → "sparse (FTS) retrieval failed" → "retrieval unavailable; serving popular fallback" → `repo.ensure_user()` → `PendingRollbackError` → 500. **Pre-existing bug:** the cancelled query invalidates the request's SHARED session; retrieval degrades correctly but never rolls the session back, so the sparse fallback and the history write both fail and a designed "degraded, 200" becomes a 500. Postgres shows 1 connection "idle in transaction" (likely leaked). Trigger: the dense query now exceeds its time limit on this machine (same slowness as the 17-min vLLM load); queries at 06:51 / 07:08 succeeded. **CI also noted:** the web job's build succeeded and printed `ƒ (Dynamic) server-rendered on demand` (R2 confirmed in CI); the job fails only in `Post Run setup-node` (pnpm cache path does not exist). trivy-action tags are v-prefixed now (`v0.36.0` ...), so `0.28.0` is gone · **Timing evidence:** `EXPLAIN ANALYZE` of the pgvector query on 269 rows = **2,039 ms** (retriever limit `timeout_seconds=2.0` in `hybrid.py`) — so every dense search is cancelled; the same distance computation measured **50 ms** a minute later. Plain SQL `sum(generate_series(1,3M))` 470 ms, numpy 1536x1536 matmul 1.28 s, numpy cosine 269x1536 2.07 ms; the VM exposes AVX-512. **Conclusion:** the Docker VM has intermittent bursts of severe slowness (also the 17-min vLLM weight load and the 105 s api start); a SIMD-only cause is NOT confirmed. The leaked connection was `idle in transaction` for 10 min 44 s. Fix direction: roll the session back after a failed retrieval leg so a slow burst yields a degraded 200, not a 500 · **F1 applied 2026-09-14, test first:** new real-Postgres test `tests/integration/test_session_recovery.py` — **before the fix** 1 passed (a query cancelled by `asyncio.wait_for` leaves the session raising `PendingRollbackError`, the production mechanism reproduced) + 1 failed (no recovery hook); **after** 2 / 2 pass. Fix: `HybridRetriever(on_leg_failure=…)` runs the hook after each failed leg (a failing hook is logged, never masks the fallback); `RetrievalPipeline` passes `session.rollback`. Safe to roll back: nothing writes to the request session before retrieval (quota uses its own counter; history + usage writes come after) and no `SET LOCAL` / tenant setting exists anywhere. Unit tests: +4 in `test_hybrid_resilience.py` (recover before sparse, both legs down → 2 recoveries + raise, failing hook, healthy → never called) + new `test_pipeline_session_recovery.py` (2; red check: with the wiring removed it raises `RetrievalUnavailableError`, the production chain). **Checks:** unit suite 334 passed, ruff + format clean, mypy clean, CRLF kept · **Second leak path found:** the idle-in-transaction connection belongs to the api (172.18.0.7), opened 09:32:48 — seconds before the first 500 — and its last statement is `select pg_catalog.version()`, SQLAlchemy's first-connect setup: most likely cancelled by the 2 s leg timeout while the connection was still being set up, which a session rollback cannot reach. Held 41+ min; closes when the api is recreated. Watch whether it recurs · **CLOSED 2026-09-16 — live PASS:** the interrupted rebuild did finish (anime-api:latest built 15 Sep 05:38 UTC, after the fix); the running container carries it (`on_leg_failure` in HybridRetriever and `session.rollback` in RetrievalPipeline both confirmed inside the container). 6 live app queries: **6/6 HTTP 200, 0 PendingRollbackError, 0 failed retrieval legs, 0 idle-in-transaction connections**, and the second leak did not recur. **Honest limit:** the VM was fast on 16 Sep, so the original trigger (a dense query exceeding 2.0 s) never fired — the failure path itself is reproduced only by the integration test, not live

> **Open follow-up (not blocking):** `make up-sglang` total is now 458 s (under the 600 s the user saw in another app). SGLang's fixed cost on this card is prefill CUDA-graph capture, 316–396 s on every start (206 s on the other project's `tp-sglang`); weight load varies 12–401 s. The longest runs also included a one-time ~13 min image rebuild after a code change. Options if it matters: keep the engine running (`make up-sglang` reuses a running SGLang), or measure `--disable-prefill-cuda-graph` startup vs TTFT (P5 measured TTFT p50 3.31 s with eager prefill)

---

## TRACK O — Observability / Grafana expansion ✅ 9 / 9

> Requested 2026-09-16: "measure every switch, monitor every component", panels reordered and
> self-explaining. Format model: P5-Medical-Chatbot's `medbot-overview.json` (44 panels, row
> sections, every panel documented, SLO-framed). Scope approved: **all of it, staged**; layout:
> **one overview + two deep-dives**.
>
> **Baseline measured before design:** Prometheus scraped only 2 targets (the OTel collector and
> itself). The app emits 12 series (`anime_*`) plus HTTP semconv; there were **no** database, cache,
> container, host or inference-engine metrics at all. The running vLLM already exposes **354 metric
> lines** (TTFT, TPOT, KV-cache utilisation, queue depth, prefix-cache hits) that nothing was reading.

- ✅ O.1 **Scrape coverage** — `infra/observability/prometheus.yml` rewritten: 12 jobs (app via collector, collector self-telemetry, venue engine via the `anime-venue` network alias, both Postgres, both Redis, MinIO, ClickHouse, cAdvisor, node-exporter, Grafana, Prometheus), `external_labels` so the same dashboards work against a cluster, and a documented contract that legitimately-absent targets stay DOWN rather than being deleted. **Verified live 2026-09-16: 13 / 13 targets UP** (app, collector self-telemetry, venue-engine via the alias, both Postgres, both Redis, MinIO, ClickHouse, cAdvisor, node-exporter, Grafana, Prometheus)
- ✅ O.2 **Exporters in the obs tier** — postgres-exporter x2 (app + Langfuse), redis-exporter x2, cAdvisor (per-container CPU/mem/IO), node-exporter (the Docker VM itself — this host has already produced a 17-min model load and a 2,039 ms pgvector query that no app metric explains). **All 4 images pull and are digest-pinned**: postgres-exporter `sha256:6999a765…`, redis_exporter `sha256:120f7ec7…`, cadvisor `sha256:3cde6faf…`, node-exporter `sha256:4032c6d5…`. **Live:** all 6 containers up, added to `OBS_SERVICES` so `make up-obs` starts them, host ports 1022-1027. **Defect found and worked around — per-container metrics are impossible on this host:** cAdvisor cannot identify containers because Docker Desktop's **containerd image store** leaves `/var/lib/docker/image` without a `layerdb` (`failed to identify the read-write layer ID`), and it is not given the per-container cgroups either — it sees only `/`, `/docker`, `/docker/buildkit`. Neither `--disable_metrics` nor raw cgroup mode recovers them. The container row now reports containers-vs-VM in aggregate and says so in every panel; turning off "Use containerd for pulling and storing images" in Docker Desktop restores the per-container split with no dashboard edit
- ✅ O.3 **Endpoints that must be switched on** — collector self-telemetry on `0.0.0.0:8888` (published as 1028), `MINIO_PROMETHEUS_AUTH_TYPE=public`, ClickHouse `prometheus.xml` on 9363 — all three scraped and returning data. ClickHouse's endpoint lives in its own config file, not `cluster.xml`, so a syntax error there cannot stop the server booting
- ✅ O.4 **App metric gaps (code + tests)** — cache hit/miss (the cached service has no counter, so hit rate cannot be graphed), retrieval stage latency (embed / dense / sparse / rerank / MMR), rerank timeouts as a first-class counter (L.15's root cause is currently only visible in logs), circuit-breaker state, quota rejections by scope · **Implemented 2026-09-16:** 4 new instruments (`anime.cache.lookups`, `anime.retrieval.stage.duration`, `anime.circuit.transitions`, `anime.quota.rejections`) wired at 9 call sites across `cached_service.py`, `hybrid.py`, `pipeline.py`, `resilience.py`, `quota.py`. Failed and timed-out stages are recorded WITH the time they burned, and labelled `timeout` vs `error` — a stage that costs its full budget on every request is the expensive kind of working. Breaker transitions fire only on an actual state CHANGE (a per-call counter would bury the signal). **+10 tests** (call-site tests, not OTel tests: an instrument that exports cleanly and is never reached renders an empty panel that reads exactly like "nothing is happening"). Suite 344 passed, ruff + mypy clean · **Defect found by reading the exported data, not the dashboard (2026-09-16):** `anime.retrieval.confidence` is a probability in (0,1) but had no View, so it used OTel's default boundaries `[0, 5, 10, 25, ...]` — every possible value is <= 1, so **every sample landed in the single "<= 5" bucket** and the LLM dashboard's percentile panels and threshold comparison were computed from a one-cell distribution. This is the same trap `DURATION_BUCKETS_SECONDS` was created for, and it predates Track O: the confidence panels could never have worked. Fixed with `CONFIDENCE_BUCKETS` (16 boundaries, tight around **0.731** — the sigmoid of the routing threshold — because the question the histogram answers is how far live traffic sits from the cutoff), plus a View for the new stage histogram on the existing seconds scale, plus a test mirroring the duration-bucket one. Suite **345 passed**
  - **Live proof the new metrics flow (2026-09-16, api rebuilt, 2 real queries):** `anime_cache_lookups_total` 2 misses; all five stages recorded `ok` — embed, dense, sparse, **rerank**, mmr; 2 confidence samples. **Two numbers that change the L.15 picture:** mean rerank **1.053 s against a 2.0 s budget** (it fits comfortably on a healthy host — the earlier timeouts were the degraded-host case), and mean confidence **0.612**, below the 0.731 cutoff. So on this corpus the venue is not starved by a broken reranker; these queries are simply not confident enough to route. `venue_decisions` stayed empty because `make up` runs API-LLM mode with routing off
  - **Bucket fix verified live 2026-09-16 (api rebuilt, 3 in-corpus queries):** the confidence histogram now reports **17 boundaries** with samples spread across them (2 <= 0.85, 5 <= 0.95) instead of a single `<= 5` cell, and the percentile panels finally compute: **p50 0.925, p90 0.945 — both ABOVE the 0.731 routing cutoff**. Stage p95 went from a uniform 4.75 s bucket artifact to real numbers: **rerank 1.45 s, embed 0.725 s, dense 0.0097 s, sparse 0.0047 s, mmr 0.0047 s** — rerank is ~2/3 of retrieval time and sits inside its 2.0 s budget with little headroom, which is precisely why a slow host tips it into timeout and silently disables venue routing. **This reopens L.15 as provable:** earlier queries measured 0.612 mean confidence, but in-corpus queries score ~0.93, comfortably over the threshold
- ✅ O.5 **Dashboard 1 — overview** (`api-overview`, 21 panels / 6 rows): is it working → what is it serving → where the time goes → what it costs → who answered → what is broken underneath. Replaces the old 14-panel API Overview in place, so the uid and any links survive
- ✅ O.6 **Dashboard 2 — LLM & venue routing** (`anime-llm-venue`, 21 panels / 4 rows):: decisions by outcome, confidence distribution vs the 0.731 sigmoid threshold, venue vs hosted latency and cost, engine internals (KV cache, queue depth, TTFT/TPOT, prefix-cache hit rate, finish reasons). Includes the three panels that would have diagnosed L.15 in one glance: confidence samples/sec, rerank timeouts/sec, and confidence percentiles against the 0.731 line
- ✅ O.7 **Dashboard 3 — infrastructure** (`anime-infra`, 28 panels / 6 rows): scrape health, both Postgres (connections, commit/rollback, buffer hit ratio, longest transaction, size), both Redis (hit rate, memory, evictions, commands, clients), containers in aggregate, the Docker VM (CPU by mode, load, memory, disk busy, filesystem), MinIO, ClickHouse and the collector pipeline
- ✅ O.8 **Surface it** — `scripts/service_ls.sh` gains a METRIC EXPORTERS section (7 rows incl. the venue engine, which is matched by container name since `anime-venue` is only a network alias) and lists the three dashboards; new **`docs/OBSERVABILITY.md`** (how metrics get there, the scrape table, every app metric and why it exists, the fail-safe routing explanation, the cAdvisor limitation, how to add a panel); README links it
- ✅ O.9 **Per-provider sections (requested 2026-09-16, sample: P5's medbot dashboard):** four collapsible rows on the overview — **5a vLLM, 5b SGLang, 5c Groq, 5d OpenAI** — each minimised by default with calls/sec, request p95, TTFT p50/p95, cost per request, error rate, latency percentiles and tokens/sec, plus engine internals for the two self-hosted rows (up, running/waiting, KV cache, engine TTFT/TPOT, throughput, queue vs e2e, prefix-cache hit rate). Grafana only collapses a row whose panels are NESTED inside it, so the generator gained a `collapsed_row`; a flat row with `collapsed: true` hides nothing. **Blocker found and fixed first — the data did not exist:** cost and tokens were attributed per model but TIME never was, and the OTel HTTP client instrumentation on this stack emits **no peer/host label at all** (verified: every `http_client_duration` series carries only method/scheme/status), so the old "Outbound provider latency p95 by host" panel grouped by a label that is never present and could never answer "is it us or them". Added `anime.llm.duration` {model, outcome} and `anime.llm.ttft` {model} recorded at `_LangChainClient` — the single seam **every** provider passes through (vLLM, SGLang, Groq and OpenAI all subclass it), so one call site covers all four — with seconds-scale bucket views and **+4 tests**. Failed calls are recorded as `outcome=error` with the time they burned; TTFT is recorded once per stream, before the first token is yielded, so a consumer that abandons the stream still contributes the measurement it caused. The broken panel was replaced by "LLM latency p95 by model", which uses the new histogram. **Honest limit:** both self-hosted engines serve the SAME model name, so the app-level panels in 5a and 5b cannot tell vLLM from SGLang — the engine panels can, and every panel in those rows says so. Dashboard totals now **118 panels** (overview 69 / LLM 21 / infra 28), every one documented, **89 queries return data, 0 error**

> **Dashboard quality gate (2026-09-16):** every one of the 70 panels carries a description, and every PromQL expression was executed against the live Prometheus: **83 queries return data, 0 error.** The 8 that return nothing are the new O.4 metrics awaiting an api rebuild plus events that have not happened yet (unpriced calls, breaker trips). Ratio panels use `or vector(0)` on both sides so an unused counter reads 0 instead of "No data", which otherwise looks like a broken panel.

---

## TRACK D — user-side async ⏳

- ✅ D.1 HF token
- ✅ D.2 Qwen2.5-7B-AWQ weight download — **COMPLETE** (5.2 GB verified in `vllm-hf-cache` volume)
- ⏳ D.3 DigitalOcean account + apply $200 credit
- ⏳ D.4 AWS account + GPU quota request
- ✅ D.5 `kind` + `kubeconform` install — verified 2026-09-13: kind v0.32.0, kubeconform v0.7.0
- ⏳ D.6 Docker Hub account + repo for public mirror (P6.2.2)
- ✅ D.7 Clerk dev JWT — `scripts/dev_token.py` proven working during S21.10 live verification (tokens expire ~1 h, re-mint as needed)
- ✅ D.8 Stop the medbot / voyantra kind clusters auto-starting at boot — **diagnosed**: all 7 node containers carry `restart=on-failure:1` (kind sets it so clusters survive a Docker restart). Fix: `docker update --restart=no` on those containers, or `kind delete cluster` if a cluster is no longer needed · **Resolved 2026-09-14:** no kind containers exist any more (0 medbot / voyantra nodes), so nothing can auto-start; the clusters were removed outside this session

---

## Status summary

| Phase | Status | Blocking on |
|---|---|---|
| 0–3 | ✅ Complete | — |
| 4 | ✅ 21 / 21 | — |
| 5 | ✅ Complete | — |
| 6 | 🔄 4 / 12 | R1–R6 approved; R2 implementation approved 2026-09-14 (queued after Track L items) |
| 7 | 🔄 2 / 6 | Gate answers (kind + kubeconform now installed) |
| 8 | ⏳ 0 / 12 | Phase 6 complete; DO credit (D.3) |
| 9 | ⏳ 0 / 9 | Phase 6 complete; AWS quota (D.4) |
| 10 | ⏳ 0 / 6 | Everything above |
| L | 🔄 15 / 16 | L.15 only: the venue cannot be exercised on this host — reranking 20 candidates exceeds RERANK_TIMEOUT=2.0s, so confidence is None and routing fails safe to hosted |

**Totals:** 6 phases complete (0, 1, 2, 3, 4, 5) · **156 items done · 46 pending · 0 blocked**.
All development and hardening is finished. Everything remaining is deployment
(Phases 6–9) plus the portfolio writeup, gated only on user-side accounts in Track D.
