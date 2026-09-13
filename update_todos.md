# Update Todos — Anime Recommender

> Living tracker. Long-form plan with rationale: `Documents/docs/transformation-plan.md`
> Decision record: `docs/DECISION_LOG.md`

**Legend:** ✅ complete · 🔄 in progress · ⏸️ blocked · ⏳ pending
**Last updated:** 2026-09-12 — Phase 6 open (1/12). Gates: G1=B PAT auth · G2=B lockfile · G3=A layered values · G4=A chart=app version · G5=C cd.yml untouched

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

## PHASE 6 — Release Packaging 🔄 1 / 12

> "Build once, deploy many." One immutable signed artifact set, consumed unchanged by Phases 7/8/9.
>
> **Gates locked:** G1=B PAT registry auth (cosign signing stays keyless — separate OIDC token) ·
> G2=B digests in a lockfile · G3=A layered values · G4=A chart version = app version ·
> **G5=C `cd.yml` left untouched** — two pipelines publish independently, so "same digest
> everywhere" is FALSE until resolved. **Recorded as a Phase 9 blocker for P9.5's portability proof.**

- ✅ P6.1 Reproducible builds — **`base-images.lock`** at repo root, shell-sourceable, pins `uv` + `node` by sha256 digest. All 3 Dockerfiles annotated that the lock is authoritative and the tag default is an unpinned fallback. `scripts/release/refresh_base_images.sh` + `make base-images-check|refresh`
  - ✅ P6.1a **Bug found by running it under make** — `docker` inside the `while read` loop consumed the loop's stdin, so it processed one entry then died. Works interactively (TTY), fails under make/CI — exactly where the gate runs. Fixed with `< /dev/null`; verified under TTY, make and piped stdin
- ⏳ P6.2 Dual registry setup
  - ⏳ P6.2.1 `ghcr.io` — deployment source of truth; **PAT auth per G1=B** (note: `GITHUB_TOKEN` + `packages: write` would need no stored credential)
  - ⏳ P6.2.2 Docker Hub — public showcase mirror only; never a cluster pull source
- ⏳ P6.3 Tagging — `:<git-sha>` immutable + `:vX.Y.Z` semver; `:latest` local-only
- ⏳ P6.4 SBOM (syft) + vulnerability scan (trivy) gating the push
- ⏳ P6.5 **Cosign keyless signing** (Sigstore/Fulcio/Rekor via GitHub OIDC) + verification policy
- ⏳ P6.6 Helm chart → OCI artifact on `oci://ghcr.io/ghourimarti/charts`, signed, version-pinned
- ⏳ P6.7 Values matrix — `values.yaml` base + `values-local` / `values-doks` / `values-aws` deltas
- ⏳ P6.8 `make package` — full release bundle + `RELEASE.md`
- ⏳ P6.9 Render-verify all three targets — `helm template | kubeconform -strict`
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
  - ⏳ P7.3.1 `values-local.yaml` — ESO off, Rollout off, Ingress off, `IfNotPresent`
  - ⏳ P7.3.2 `scripts/deploy/up_local_k8s.sh` — idempotent stand-up
  - ⏳ P7.3.3 `scripts/deploy/down_local_k8s.sh` — teardown (+ `--soft`)
  - ⏳ P7.3.4 `scripts/deploy/smoke_k8s.sh` — via `kubectl port-forward`
  - ⏳ P7.3.5 `deploy/stage2-local-k8s.md`
  - ⏳ P7.3.6 Makefile — `k8s-render`, `k8s-up`, `k8s-down`, `deploy-stage2`
  - ⏳ P7.3.7 `helm template | kubeconform -strict` clean
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

## TRACK D — user-side async ⏳

- ✅ D.1 HF token
- ✅ D.2 Qwen2.5-7B-AWQ weight download — **COMPLETE** (5.2 GB verified in `vllm-hf-cache` volume)
- ⏳ D.3 DigitalOcean account + apply $200 credit
- ⏳ D.4 AWS account + GPU quota request
- ⏳ D.5 `kind` + `kubeconform` install (for P7.3)
- ⏳ D.6 Docker Hub account + repo for public mirror (P6.2.2)
- ✅ D.7 Clerk dev JWT — `scripts/dev_token.py` proven working during S21.10 live verification (tokens expire ~1 h, re-mint as needed)

---

## Status summary

| Phase | Status | Blocking on |
|---|---|---|
| 0–3 | ✅ Complete | — |
| 4 | ✅ 21 / 21 | — |
| 5 | ✅ Complete | — |
| 6 | ⏳ 0 / 10 | Nothing — ready to start |
| 7 | 🔄 2 / 6 | Gate answers + `kind` install (D.5) |
| 8 | ⏳ 0 / 12 | Phase 6 complete; DO credit (D.3) |
| 9 | ⏳ 0 / 9 | Phase 6 complete; AWS quota (D.4) |
| 10 | ⏳ 0 / 6 | Everything above |

**Totals:** 6 phases complete (0, 1, 2, 3, 4, 5) · **96 items done · 55 pending · 0 blocked**.
All development and hardening is finished. Everything remaining is deployment
(Phases 6–9) plus the portfolio writeup, gated only on user-side accounts in Track D.
