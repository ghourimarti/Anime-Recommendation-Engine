# Update Todos (complete)

**Totals: 198 done · 38 pending · 1 in progress · 3 blocked · 7 phases complete (0–6)**

## PHASE 0: Recon ✅ 3/3
- ✅ P0.1 Read repo, map stack
- ✅ P0.2 Baseline report
- ✅ P0.3 Package mapping (Package 1, RAG)

## PHASE 1: Requirements & NFRs ✅ 3/3
- ✅ P1.1 Functional scope
- ✅ P1.2 NFRs @ 100k MAU
- ✅ P1.3 Out-of-scope list

## PHASE 2: Decision Log ✅ 5/5
- ✅ P2.1 Dependency graph
- ✅ P2.2 22 decisions
- ✅ P2.3 At-a-glance table
- ✅ P2.4 D5/D6/D11 revisions
- ✅ P2.5 D4b added + D12 amended

## PHASE 3: Transformation Plan ✅ 4/4
- ✅ P3.1 18 steps
- ✅ P3.2 v1.1 deployment split
- ✅ P3.3 v1.2 GPU spikes
- ✅ P3.4 v1.3 Phase 6 inserted

## PHASE 4: Execution ✅ 21/21
- ✅ S1 skeleton
- ✅ S2 ingestion + pgvector
- ✅ S3 hybrid retrieval + rerank + MMR
- ✅ S4 eval harness
- ✅ S5 tiered LLM client
- ✅ S6 FastAPI
- ✅ S7 Redis cache
- ✅ S8 circuit breakers
- ✅ S9 Clerk + multi-tenant
- ✅ S10 quota + cost meter
- ✅ S11 observability
- ✅ S12 Next.js UI
- ✅ S13 Docker + compose
- ✅ S14 SQS workers + KEDA
- ✅ S15 Terraform
- ✅ S16 Helm + ArgoCD + Rollouts + ESO
- ✅ S17 CI + eval gate
- ✅ S18 k6 + docs
- ✅ S19 vLLM spike
  - ✅ S19.0 hardware recon
  - ✅ S19.1 disk cleanup
  - ✅ S19.2 GPU passthrough
  - ✅ S19.3 model decision
  - ✅ S19.4 image pull
  - ✅ S19.5a UVA fix
  - ✅ S19.5b HF token
  - ✅ S19.5c weights
  - ✅ S19.6 measurement
    - ✅ 6a harness
    - ✅ 6b harness bugs
    - ✅ 6c baseline 67.9 tok/s
    - ✅ 6d host-contention root cause
  - ✅ S19.7 GPU_VENUE.md
  - ✅ S19.8 commit prep
- ✅ S20 SGLang spike
  - ✅ S20.1 image
  - ✅ S20.2 cache reuse
  - ✅ S20.3 server up
  - ✅ S20.4 .env toggle
  - ✅ S20.5 measured 69.8 tok/s
  - ✅ S20.6 A/B compare
  - ✅ S20.7 docs
  - ✅ S20.8 D4b
  - ✅ S20.9 commit prep
- ✅ S21 Multi-venue integration
  - ✅ S21.0 zero-rate cost
  - ✅ S21.1 VenueClient
  - ✅ S21.2 config
  - ✅ S21.3 wiring
  - ✅ S21.4a confidence measured
  - ✅ S21.4b threshold 1.0
  - ✅ S21.4c fail-safe router
  - ✅ S21.5 breaker
  - ✅ S21.6 fall-through
  - ✅ S21.7 observability
  - ✅ S21.8 eval regression
    - ✅ 8a harness choice
    - ✅ 8b control pass
    - ✅ 8c noise floor
    - ✅ 8d Poisson margin
    - ✅ 8e 111×3 PASS
  - ✅ S21.9 19 tests
  - ✅ S21.10 flag ON live
    - ✅ 10a histogram sigmoid
    - ✅ 10b phrasing sensitivity
    - ✅ 10c container networking

## PHASE 5: Hardening ✅ 5/5
- ✅ P5.1 audits
- ✅ P5.2 load test
- ✅ P5.3 chaos
- ✅ P5.4 backup drill
- ✅ P5.5 ops
  - ✅ P5.5.1 runbooks
  - ✅ P5.5.2 alert routing
  - ✅ P5.5.3 cost thresholds
  - ✅ P5.5.4 log retention
  - ✅ P5.5.5 RTBF

## PHASE 6: Release Packaging ✅ 12/12
- ✅ P6.1 base-images.lock
  - ✅ P6.1a stdin bug under make
- ✅ P6.2 dual registry
  - ✅ P6.2.1 ghcr.io (PAT)
  - ✅ P6.2.2 Docker Hub mirror
- ✅ P6.3 tagging
- ✅ P6.4 SBOM + Trivy
- ✅ P6.5 cosign keyless
- ✅ P6.6 OCI chart
- ✅ P6.7 values matrix
  - ✅ 7a empty prod tag
  - ✅ 7b dead canary steps
  - ✅ 7c EKS NetworkPolicy
  - ✅ 7d ApplicationSet regression
  - ✅ 7e docs
- ✅ P6.8 make package + RELEASE.md
- ✅ P6.9 render-verify
  - ✅ 9a pipefail
  - ✅ 9b offline schemas
  - ✅ 9c control checks the field
  - ✅ 9d k8s 1.31 pin
- ✅ P6.10 consumption proof on kind

## PHASE 7: Local & kind 🔄 5/6
- ✅ P7.1 images
- ✅ P7.2 compose e2e
  - ✅ P7.2.1 smoke script
  - ✅ P7.2.2 stage1 doc
  - ✅ P7.2.3 make targets
  - ✅ P7.2.4 acceptance run
  - ✅ P7.2.5 re-verify with registry images — PASS on PUBLISHED v0.1.0 digests (10/10 200s, p50 4192ms, p95 5345ms < 8000ms)
    - ✅ 5a cosign v3.1.3 installed — same version release.yml pins, so no signer/verifier skew
    - ✅ 5b all 4 artifacts verify: 3 image signatures + chart signature + 3 spdxjson SBOM attestations
    - ✅ 5c signing identity is ghourimarti/Anime-Recommendation-Engine, NOT this repo — read from the Fulcio cert SAN; user confirmed it is authoritative
    - ✅ 5d scripts/release/verify_artifacts.sh + `make release-verify`; --selftest runs 3 negative controls, all correctly reject
    - ✅ 5e compose image refs parameterized (ANIME_{API,WEB,WORKER}_IMAGE) — defaults identical, `make up` byte-for-byte unchanged
    - ✅ 5f trap caught before it bit: up-app hardcoded `--build`, which would have silently tested LOCAL bytes → APP_BUILD ?= --build
    - ✅ 5g proved it was not a local fallback: all 5 containers on @sha256: refs; published api 6e5e1701 ≠ local build 80a77408
    - ✅ 5h FINDING: published chart 0.1.0 is STALE — predates every Phase 7 chart fix → raised as the Phase 8 prerequisite below
    - ✅ 5i first time `cosign verify` has ever run outside CI; release.yml only verified its own output in the same job
- ✅ P7.3 kind + Helm
  - ✅ P7.3.1 values-local (delivered by P6.7)
  - ✅ P7.3.2 up script (+LocalStack, SQS init, svc discovery)
  - ✅ P7.3.3 down script
  - ✅ P7.3.4 smoke (PASS: 10/10 200s, p95 4493ms < 8000ms NFR)
  - ✅ P7.3.5 stage2 doc
  - ✅ P7.3.6 make targets
  - ✅ P7.3.7 kubeconform (delivered by P6.9)
  - ✅ P7.3.8 k8s ingest script — 269 titles/chunks into cluster PG
  - ✅ P7.3.9 in-cluster backup drill — PASS, 8 tables matched
  - ✅ P7.3.10 chart fix: SA as pre-install hook (-10) — migrate Job now admitted
  - ✅ P7.3.11 chart gap: LLM_PRICING added to ConfigMap — api boots
  - ✅ P7.3.12 chart gap: CLERK_JWKS_URL/ISSUER/AUDIENCE added — auth path works
  - ✅ P7.3.13 chart fix: checksum/config on api/web/worker — config change rolls pods
  - ✅ P7.3.14 full cold acceptance PASS (attempt 7): p95 5266ms < 8000ms enforced, drill 8 tables, history row recorded
  - ✅ P7.3.15 gate fix: --warmup (default 1) + --p95-budget-ms (default 8000) asserted; neg+pos controls pass
  - ✅ P7.3.16 kind lifecycle in Makefile: k8s-up/upv/down/downv/ps matching compose; stray cluster now visible in `make ps`
  - ✅ P7.3.17 kind wired INTO the compose lifecycle: make down→k8s-stop (pause, cluster kept), downv→k8s-downv (delete), up→k8s-start
    - ✅ 17a kind_power.sh stop|start — stop ≠ delete: docker stop keeps etcd (resume 59s), kind delete costs ~5min + 4GB image reload
    - ✅ 17b my own gate defect: start reported "ready" on NODE status while postgres/api/localstack were 0/1 — re-pointed at pod readiness
    - ✅ 17c recovery is NOT monotonic (9/11→6/11→8/11→11/11) — gate requires 2 consecutive all-ready polls, not the first
    - ✅ 17d skip paths exit 0 (no kind / no cluster / empty ns) so `make up` never requires kind; 5 negative controls pass, usage error still EXIT=2
    - ✅ 17e resume is functionally lossless: stage2 smoke PASS after stop/start (10/10 200s, p95 1678ms, 269 chunks intact)
- ✅ P7.4 probes / HPA / DNS
  - ✅ P7.4.1 metrics-server pinned v0.7.2 + --kubelet-insecure-tls into up script
  - ✅ P7.4.2 api HPA added (2-10 @ 70% CPU; scaleTargetRef follows rollout toggle)
  - ✅ P7.4.3 api startupProbe (5s x 30 = 150s; measured start->Ready 10.0s)
  - ✅ P7.4.4 chart defect: replicas omitted when an HPA owns it (api + web)
  - ✅ P7.4.5 verify_k8s.sh — 14 assertions, PASS; DNS + arg negative controls
  - ✅ P7.4.6 k8s-verify wired into deploy-stage2 + help
  - ⏳ P7.4.7 P8.9 follow-up: CPU is a weak HPA signal for an I/O-bound api
- ✅ P7.5 failure drills
  - ✅ P7.5.1 k8s_probe_loop.sh — in-cluster probe (port-forward would measure the instrument)
  - ✅ P7.5.2 k8s_drill.sh — pod-kill / rollout-restart / node-drain, measured under load
  - ✅ P7.5.3 defect #10 preStop hook: pod-kill 1/119 -> 0/119, restart 3/176 -> 0/176
  - ✅ P7.5.4 defect #12 migrate-Job had no resource requests -> helm UPGRADE always failed
  - ✅ P7.5.5 PDB added (cloud-only; blocks drains on 2-node kind)
  - ⏳ P7.5.6 topologySpread ScheduleAnyway does NOT spread in practice — replicas still co-locate
  - ⏳ P7.5.7 node-drain drill confounded by node-bound local-path PV; re-run in P8.10 (external DB)
  - ✅ P7.5.8 Makefile k8s-chaos targets (outside deploy-stage2, mirrors chaos-*)
- 🔄 P7.6 terraform plan — PARTIAL (credential-free half green; plan blocked)
  - ✅ P7.6.1 fmt -check -recursive clean; init -backend=false + validate: "configuration is valid"
  - ✅ P7.6.2 static count: 52 resource blocks / 10 modules (expect 80-120 planned after count/for_each)
  - ✅ P7.6.3 stage3-terraform-plan.md — plan-review checklist + the bootstrap ordering dependency
  - ✅ P7.6.4 make tf-check (credential-free gate)
  - ✅ P7.6.5 tflint + trivy installed and wired into make tf-check (gate verified by negative control)
    - ✅ 5a tfsec REJECTED as deprecated (archived into Trivy, already a CI dep) — trivy config instead
    - ✅ 5b tflint 23 findings -> 0: versions.tf for all 10 modules; dead vpc_id var removed
    - ✅ 5c trivy AWS-0039 FIXED: EKS had NO secrets envelope encryption (+KMS key, rotation, 30d window)
    - ✅ 5d trivy AWS-0095 fixed (SNS encryption) — traded for AWS-0136 (CMK), accepted with reason
    - ✅ 5e .trivyignore baseline: 4 accepted HIGH/CRITICAL, each with a written reason + revisit trigger
    - ✅ 5f my own decorative gate: `cmd && run || echo` swallowed trivy failures; fixed to if/then/else
  - ⛔ P7.6.6 terraform plan — BLOCKED: InvalidClientTokenId + backend bucket/lock table do not exist (Track D.4)

## PHASE 8: Managed K8s (DOKS) ⏳ 0/13
- ⛔ P8.0 PREREQUISITE — re-release as v0.1.1 before Phase 8 consumes anything. Published chart 0.1.0 predates ALL Phase 7 chart fixes:
  no LLM_PRICING (api will not boot), no CLERK_JWKS_URL/ISSUER/AUDIENCE (auth broken), no migrate-Job resource requests (helm upgrade
  always fails vs the chart's own ResourceQuota), no preStop (drops requests every rolling deploy), no checksum/config, no api-hpa.yaml,
  no pdb.yaml, no startupProbe, no topologySpreadConstraints. Signature is VALID — signing proves provenance, not correctness.
  Images v0.1.0 are fine (Phase 7 fixes were chart-only, proven by P7.2.5). Needs a git tag, which only you run. Gates P8.7.
- ⏳ P8.1 vendor + cost
- ⏳ P8.2 Terraform cluster
- ⏳ P8.3 pull secret
- ⏳ P8.4 data tier
- ⏳ P8.5 ingress + TLS
- ⏳ P8.6 secrets
- ⏳ P8.7 helm install
- ⏳ P8.8 observability
- ⏳ P8.9 load
- ⏳ P8.10 chaos
- ⏳ P8.11 $/1k queries
- ⏳ P8.12 teardown

## PHASE 9: AWS EKS ⏳ 0/10
- ⏳ P9.1 account + quota
- ⏳ P9.2 VPC + EKS
- ⏳ P9.3 IRSA
- ⏳ P9.4 RDS / ElastiCache / SQS / ESO
- ⏳ P9.5 same digests, config-only diff
- ⏳ P9.6 GPU nodes
- ⏳ P9.7 ArgoCD + canary rehearsal
- ⏳ P9.8 cost comparison
- ⏳ P9.9 findings
- ⏳ P9.10 ESO Secret vs migrate-hook ordering (same class as P7.3.10; found in P7.3)

## PHASE 10: Portfolio ⏳ 0/6
- ⏳ P10.1 diagram
- ⏳ P10.2 README
- ⏳ P10.3 metrics story
- ⏳ P10.4 findings
- ⏳ P10.5 demo
- ⏳ P10.6 talking points

## TRACK I: Inspection & observability audit ✅ 17/17  (2026-09-21)
- ✅ I.1 Discovery — 19 anime_* metrics, 3 dashboards/118 panels, 2 cache layers, no Jaeger
- ✅ I.2 `Documents/docs/INSPECTION_ROUND2.md` — battery + 3-instrument guide (427 lines;
        +Q11c the rerank split, +Q11d the fix, +Q13 which model actually answered)
- ✅ I.3 `Documents/docs/INSPECTION_ROUND3.md` — full manual, every metric + panel (603 lines;
        +entries for rerank.compute and runtime.loop_lag, +the attribution table)
- ✅ I.4 `scripts/_inspect_common.py` + `_inspect_sections.py` — engine + 12 sections
- ✅ I.5 `scripts/inspect_stack_{vllm,sglang}.py` — one command, exit code = FAILs
- ✅ I.6 `scripts/cache_ctl.py` + `make cache-ls|cache-clear|cache-clear-all` (quota survives)
- ✅ I.7 Verified live: 48 passed / 4 FAILED / 12 info; selftest 6/6; sglang entrypoint
        correctly FAILs engine identity while vLLM holds the GPU
- ✅ I.8 I.F1 investigation → finding WITHDRAWN + battery corrected. Added a clear-class
        probe, replaced the "threshold uncalibrated" verdict with `confidence spans the
        threshold` (now passes, p99 0.983 vs 0.731), added `rerank headroom vs its timeout`
        (FAILs at 84%). Both documents corrected in §1.2/§1.3/Q11/Part 5.2/Part 6.
        4 of my OWN bugs caught by running it: one-shot containers read as stopped;
        `p()` read .env for compose-only config; injection check flagged the ECHOED query
        as a leak; 18s wait missed the second metric lag
- ✅ I.9 I.F1b parts **A (split the metric) + B (hunt contention)** — built, run, and the
        measurement **disproved my own hypothesis**. 5 source files + 3 test files, 12 new
        tests, 5 new Grafana panels, 4 new inspection checks, 4 new selftest controls.
        A: `anime.retrieval.rerank.compute` times `model.predict` alone (model load moved
        OUTSIDE the timer; `warm()` no longer routes through `score()`).
        B: `loop_monitor` samples event-loop lag every 250ms via `anime.runtime.loop_lag`.
        Behaviour unchanged — no timeout touched, comment-only edit to pipeline.py.
        3 of my OWN bugs caught by running it: both new histograms shipped with NO View
        (so OTel's millisecond defaults -> "p95 9.5s" for a 2.4s stage); the split check
        PASSED on a physically impossible "204% model"; the 30m window silently merged old
        and new `le` boundaries after the rebuild.
        **Final acceptance (api rebuilt, SGLang on the GPU, clean window): 49 passed /
        8 FAILED / 12 informational; selftest 10/10; suite 361 passed.** All four new
        checks green: buckets stable · split **100% model** (compute p95 1.838s == wall
        p95 1.838s) · sampler live · loop p99 **1.3ms**. The 8 FAILs: 3 are one missing
        SGLang flag (I.F8), 2 are the rerank headroom finding counted twice (I.F1b,
        80% of budget), 1 is Groq's error rate (I.F9), 1 is p95 6.25s vs the 6s NFR,
        and 1 is a quota counter left over from my own load testing.
- ✅ I.10 **I.F6 root-caused — measurement only, nothing changed.** Ran the out-of-corpus
        query 12x with the cache cleared between runs and a per-run `X-Request-ID` (the
        middleware propagates it), then correlated every answer against its own log lines.
        Result: a **perfect 12/12 split by which model answered** — Groq's gpt-oss-20b
        refused 9/9, OpenAI's gpt-4o-mini answered 3/3, and those 3 are exactly the runs
        where Groq raised a tool-binding error. 0.45% chance by coincidence. So the
        "flaky guardrail" is really **two tiers with different refusal policies plus a
        silent fallthrough** (I.F6 + I.F9 rewritten accordingly). Also ruled OUT sampling
        (temperature is 0.0 on every path) and established a secondary effect: all 4
        rerank-timeout runs refused, because a timeout drops the pipeline to hybrid order
        and changes the prompt. Documented as Q13 in INSPECTION_ROUND2.md, including why
        a single-draw probe cannot catch a 75/25 split.
- ✅ I.11 **I.F1b FIXED — rerank headroom bought, with zero measured quality loss.**
        The lever was none of the three I had named. Benchmarked in-container on the same
        20 real candidates the model choice was originally measured on (avg 962 chars):
        thread count is already optimal (8 threads 0.91s; 16 -> 1.64s and 4 -> 1.51s are
        both WORSE, so there was no free win there), but `max_length` dominates.
        Ran the golden-set gate at each setting — the same gate that caught the L-6
        regression — rather than reasoning about it:
          512 (old): 0.91s · success@1 0.653 · lift +0.050 · PASS
          **256 (new): 0.66s · success@1 0.653 · lift +0.050 · PASS  <- 28% faster, identical**
          128:       0.28s · success@1 0.604 · lift +0.000 · **REGRESSION, 9 metrics**
        At 128 the advanced pipeline scores exactly what NAIVE scores — reranking costs
        time and contributes nothing — so 256 is the floor, not a midpoint.
        Changed `DEFAULT_MAX_LENGTH` 512 -> 256 (+ `.env`, `.env.example`, docstring table)
        and pinned it with a test naming both failure directions. Suite **362 passed**.
        **Live after rebuild: compute p50 0.75s / p95 0.998s (was 1.0 / 1.838), 22 reranks
        with 0 timeouts, `rerank headroom vs its timeout` = 50% of budget — GREEN for the
        first time since I.8.** Venue share rose 9% -> 14% in the same run, which is the
        second-order effect I.F1b predicted: every overrun had been costing a routing
        decision. Full acceptance **51 passed / 6 FAILED / 12 info** (was 49/8/12).
        One more measurement trap caught on the way: straight after the rebuild the
        stage counter read `timeout=5` with ZERO matching log lines and zero compute
        samples over 2s. The collector's Prometheus exporter keeps a dead process's
        series for its default `metric_expiration: 5m`, so it was still publishing the
        OLD process's totals. It cleared on its own; nothing was wrong with the app.
- ✅ I.12 **I.F8 FIXED — and it was two bugs, not one.**
        (a) `scripts/venue/up_sglang.sh` now passes `--enable-metrics` (flag verified
        against the installed **SGLang 0.5.19**, not assumed). `/metrics` went 404 -> 200,
        **13/13 Prometheus targets** (was 12/13), 386 series / 82 metric names ingested,
        and the "Engine internals" dashboard row has data for the first time under SGLang.
        The file is CRLF, unlike the Python sources, so it was edited byte-faithfully —
        218 CRLF / 0 bare LF after the change, `bash -n` clean.
        (b) **The inspection check was ALSO wrong, and would have failed even with the
        flag.** It matched `{__name__=~"sglang:.*"}`, but Prometheus never stores that:
        Prometheus 3.x negotiates metric-name escaping on scrape and a modern
        prometheus_client honours it, so SGLang answers Prometheus with
        `sglang_cache_hit_rate` while answering a plain curl with `sglang:cache_hit_rate`.
        Proven against one endpoint: plain request -> 82 colon / 0 underscore; with
        `Accept: ...escaping=underscores` -> 0 colon / **82 underscore**. vLLM's older
        client ignores the negotiation, which is why `vllm:*` colon names exist in the
        index — and those are STALE, not live. Check now matches `[:_]` on both engines.
        Acceptance **53 passed / 4 FAILED / 12 info** (from 6, and from 8 before I.11).
- ✅ I.13 **I.F9 investigated — no fix shipped, deliberately.** Reproduced against the
        live provider (8 controlled calls: 8/8 parsed), tested both alternative
        structured-output bindings (`json_schema` and `json_mode` both HTTP 400 on this
        model), and found the repo had ALREADY ruled out the retry path with measurements
        (`llm_sdk_max_retries`: SDK retries cost p95 19.90s / max 24.76s vs an 8s NFR).
        Also corrected my own severity claim: `outcome=error` counts rate limits too, and
        2 of the 3 errors in the sampled container were 429s I caused myself.
        Conclusion: the parse error is an intermittent provider interop bug with no clean
        fix available here, and the thing worth changing is the I.F6 refusal divergence,
        which is a product decision rather than a defect fix.
- ✅ I.14 **I.F6 FIXED — two gates, and the calibration killed the obvious one.**
        You chose "gate refusal on retrieval confidence"; measuring it first showed that
        signal **cannot** decide the I.F6 case, so both halves were built.
        **(a) Confidence floor (`REFUSE_BELOW_CONFIDENCE`, -11.0).** Calibrated on 10
        adversarial + 59 answerable golden queries, retrieval only, no LLM calls:
          -11.00 -> recall 0.70, false-refusal **0.00**   <- shipped
          -10.75 -> recall 0.80, false-refusal 0.00 (but only 0.03 logit of margin)
           -9.50 -> recall 1.00, false-refusal 0.10
        Refuses genuinely out-of-scope input before any LLM call, so the answer no
        longer depends on which tier served it — and junk stops costing a generation.
        Fails OPEN on `confidence is None`, because that means the reranker did not RUN
        (a RERANK_TIMEOUT or cold start), not that the match is poor; the fail-closed
        reading turns a slow host into a refusal storm.
        **(b) Title-existence check (`anime_retrieval/catalog.py`, NEW).** The floor
        provably cannot catch I.F6: "tell me about Demon Slayer and Jujutsu Kaisen"
        scores **-4.339**, HIGHER than the median legitimate vague query (-4.843),
        because the corpus is full of similar shounen and the reranker correctly finds
        it. Catching that class by threshold would refuse ~1 real query in 3.
        So the check is a LOOKUP: extract the named title, match it against the 269
        stored names, refuse naming exactly what is missing. Measured over 18 queries —
        present titles **1.00**, absent ones **0.45-0.63**, descriptive queries extract
        nothing at all — so the 0.78 cutoff sits midway through a 0.37-wide gap, versus
        the floor's 0.03. Token containment is load-bearing: this corpus stores Japanese
        titles, so "Berserk" is `Kenpuu Denki Berserk` and whole-string similarity reads
        0.55 for a title that is plainly there.
        **+34 tests (396 total)**, ruff + mypy clean on 87 files. One of my own bugs
        caught by its own test: the empty (unloaded) catalogue failed CLOSED and would
        have refused every named title in the product.
        Known limit, documented in the module: an English title for a show stored under
        an unrelated romaji name is refused wrongly. The fix is an alias table, not a
        lower cutoff — lowering it re-admits the absent titles this exists to catch.
        **Live: the I.F6 query now refuses 3/3 deterministically** (was 9 refuse /
        3 answer over 12), naming both missing titles; `anime like Berserk` and
        `tell me about Cowboy Bebop` still answer, descriptive queries untouched — 8/8
        on a targeted battery. Full acceptance **56 passed / 0 FAILED / 13 info**,
        exit 0, from 8 FAILs at the start of the session.
        **Read that 0 honestly — it is not a clean bill of health.** Only one of the
        four FAILs that cleared this run was actually repaired: `stage rerank` (0/11
        timeouts, from I.11). The other three went green for softer reasons — loop lag
        landed at 14.8ms because this run had less concurrent pressure, while SGLang
        still burns **99.22%** of a core (I.F11 stands); and `LLM error rate` read 0/9
        because total LLM calls fell **41 -> 9**, since the two gates refuse before
        generation, so I.F9's intermittent bug simply had fewer chances to fire (I.F9
        stands). Fewer LLM calls is itself a real saving, but it is exposure reduction,
        not a fix.
- ✅ I.15 **I.F2 FIXED — and the SGLang dashboard row had never worked at all.**
        **(a) The false green.** Rows 5a (vLLM) and 5b (SGLang) both asked
        `max(up{job="venue-engine"})`, which is 1 for whichever engine holds the
        `anime-venue` alias — so one row was always lying. Proven live with SGLang on the
        GPU: the shared query returned **1 for both**; the replacements return **0 for
        vLLM and 1 for SGLang**. They test engine-NATIVE series presence
        (`clamp_max(count({__name__=~"vllm[:_].*"}) or vector(0), 1)`), which is the only
        thing that differs between the two.
        **(b) Six panels that could never have shown data.** 5b's engine panels (53-58)
        were written against `sglang:num_running_reqs` — the colon spelling Prometheus
        never stores (same escaping-negotiation cause as I.F8b). They were blank by
        construction, and nobody could tell because SGLang published nothing anyway until
        I.12. Renamed to the stored form and verified with live traffic: TTFT p95
        **1.95s**, throughput 3.39 prompt + 0.87 generation tok/s.
        **(c) The shared "Engine internals (vLLM / SGLang)" row was vLLM-only.** Panels
        14-19 now query both spellings and show whichever engine is live; 20-22 stay
        vLLM-only because SGLang publishes no equivalent, and each now SAYS so rather
        than reading blank for an unexplained reason.
        Verified by executing every query in all three dashboards: **162 queries, 0
        errors, 0 panels without a description.** (Two apparent errors are Grafana
        template variables — `$__range`, `$__rate_interval` — which only raw Prometheus
        rejects; both are pre-existing panels I did not touch.)
- ✅ I.16 **I.F3 + I.F4 + I.F5 closed (2026-09-21).** Three findings, three different
        shapes of fix — and one of them was correctly a documentation fix, not a code one.
        **I.F3 (cache key):** NOT a live bug. The key IS tenant-capable and isolates when
        a tenant is supplied (already tested); every v1 caller passes None deliberately,
        because answers are public and a shared entry is what makes the hit rate worth
        having. Passing the tenant "to be safe" would have destroyed the hit rate to fix
        nothing. What was actually wrong was the docstring claiming "tenant-scoped", and
        that the safety of sharing rested on an assumption nothing enforced. Corrected
        the docstring to say "tenant-CAPABLE" plus the exact leak condition, and added
        `test_response_cache_payload_is_not_user_scoped`, which pins the cached payload's
        field list — adding a user-scoped field to RecommendationResult now fails a test
        that names the cache, which is the only place that change is visible.
        **I.F4 (kill switch):** now flippable at runtime. `anime_core/killswitch.py` reads
        Redis `killswitch:llm` first and `LLM_ENABLED` second, with `make llm-off` /
        `llm-on` / `llm-switch` to throw and inspect it — no redeploy, effective on the
        next request. Deliberately **no TTL**: an expiring kill switch turns spend back on
        unattended. Both failure paths (key absent, Redis unreachable) fall back to the
        environment, which is both directions of correct: a cache blip must not take
        generation down, and must not re-enable what someone deliberately disabled.
        **+9 tests** covering every spelling of "off" and both fallback directions.
        **I.F5 (dense cold start):** `PgvectorIndex.warm()` runs one throwaway
        nearest-neighbour query in lifespan, in the session already opened for the title
        catalogue, so readiness only goes green once the first real query would succeed —
        the same contract the reranker warm-up already had. Costs no OpenAI call. Uses a
        unit vector, not a zero vector, because cosine distance against zero is undefined
        and pgvector yields NaN, which would exercise a different path from the real one.
        Suite **406 passed**, ruff + mypy clean on 88 files.
        **Both VERIFIED live 2026-09-21 after the rebuild landed.**
        I.F5: startup logs `dense (pgvector) path warmed`, and the first three requests
        of the fresh process recorded `dense ok=3` with **zero timeouts** — previously
        the first ~2 timed out on every start.
        I.F4: `make llm-off` → next request returned `degraded:llm_failed` with the
        popular fallback; `make llm-on` → `grounded` again; **container StartedAt was
        byte-identical before and after**, so nothing restarted.
        Worth knowing when you throw it: the kill switch surfaces as `degraded`, which
        is what pages someone. That is pre-existing behaviour (it already took the
        `popular_fallback(DEGRADED_NOTICE)` path) and arguably right — spend stopping
        IS something to notice — but a deliberate switch and a provider outage are
        indistinguishable in the metrics.
- ✅ I.17 **I.F7 + I.F9 closed with code; I.F10 + I.F11 closed with measurement
        (2026-09-21).** Two of these did not deserve code, and measuring first is what
        showed which.
        **I.F7:** the View guard is now proven able to FAIL — extracted so a synthetic
        source with an unviewed histogram can be fed to it, with a negative control
        asserting it names exactly that instrument. It had only ever been run against
        passing input, which is not evidence that it works.
        **I.F9:** one immediate re-ask of the SAME tier, parse failures only. Justified by
        measurement rather than instinct: the primary answers at p95 **1.28s** and the
        gpt-4o-mini fallback at **4.90s**, so a second Groq attempt is both cheaper and
        faster than the fallback it avoids. Bounded at one attempt with no backoff, and
        gated on parse-error text so a 429 or timeout still goes straight to the
        fallback — retrying those would walk back into the p95 19.90s / max 24.76s that
        `llm_sdk_max_retries()` was written to prevent. **+3 tests** including that
        constraint.
        **I.F10 + I.F11: ACCEPTED, not fixed, and the evidence says why.** See both.

### Findings raised — 13 closed (10 fixed · 1 withdrawn · 2 accepted with evidence)
- ✅ I.F1 **WITHDRAWN — my error, not the app's.** I claimed "venue never serves, threshold
        never calibrated against real traffic". Both wrong. The threshold WAS derived from
        111 golden queries (S21.4a/b: clear -0.49 / edge -3.22 / vague -4.84 / adversarial
        -11.25, monotonic) and verified live (S21.10). My battery was 100% vague-class, so
        0% venue share was CORRECT behaviour. Proof: one clear-class query flipped
        venue_served 0->1 with a Qwen delta of 1 and p99 0.594 -> 0.985.
        Lesson: judge a router on whether a CLEAR query gets through, never on share --
        share measures your query mix. Battery now carries a clear-class probe.
- ✅ I.F1b **RESOLVED 2026-09-20 (I.11) — see the fix below.** As measured in I.9:
        rerank has no headroom — p95(ok)=1.700s against a 2.0s RERANK_TIMEOUT = **85% of
        budget**, still overrunning (1/33 at low load, 4/18 under the battery), and every
        overrun costs a ROUTING decision, not just a rerank: no score ->
        should_use_venue(None) -> hosted however clear the query.
        **My CAUSE was wrong.** I claimed the stage timer was inflated by event-loop
        scheduling (wall 1.25s vs a "0.056s model"). Splitting the timer refutes it:
        wall p95 **2.2s** vs compute p95 **2.2s**, means **0.5ms apart**; loop lag p50
        0.46ms / p95 0.97ms / p99 3.5ms. Scheduling explains ~0.4% of the number.
        The cross-encoder genuinely costs ~1.0s p50 / 1.45s p95 for 20 pairs on container
        CPU. So the levers are the ones already named — fewer candidates, smaller/faster
        cross-encoder, or GPU reranking — and the L-6 model was already measured at
        -0.045 success@1. Raising the timeout still just moves latency into the request.
        **FIXED in I.11** by the one lever I had not considered: truncating each pair to
        256 tokens instead of 512. Identical golden-set score, 28% less compute, and the
        stage now sits at **50% of its timeout with 0 timeouts in 22 reranks**.
- ✅ I.F2 **RESOLVED 2026-09-20 (I.15).** "SGLang - engine up" read GREEN while SGLang
        was down, because both venue rows shared `max(up{job="venue-engine"})` — true for
        whichever engine holds the alias. Now each row tests its own engine's native
        series (verified: 0 for vLLM / 1 for SGLang while SGLang held the GPU).
        Two things found while fixing it: 5b's six engine panels used the colon metric
        spelling Prometheus never stores, so they had NEVER rendered data; and the shared
        "Engine internals" row was vLLM-only, silently blank under SGLang. Both fixed.
- ✅ I.F3 **RESOLVED 2026-09-21 (I.16) — as a documentation + guard fix, not a code one.**
        The cache key is tenant-CAPABLE and isolates correctly when a tenant is passed;
        every v1 caller passes None on purpose (answers are public, and the shared entry
        is the hit rate). So there is no leak today, and "fixing" it by passing the tenant
        would have cost the hit rate for nothing. The real defects were a docstring that
        claimed "tenant-scoped", and that the safety of sharing rested on an assumption
        nothing checked. Both addressed: the docstring now states the exact condition
        under which this leaks, and a test pins the cached payload's fields so adding a
        user-scoped one fails and points back at the cache.
- ✅ I.F4 **RESOLVED 2026-09-21 (I.16).** `LLM_ENABLED` was read from `os.environ` at
        call time and nothing writes os.environ at runtime, so stopping spend meant
        editing `.env` and restarting — during the incident, while it was still spending.
        Now Redis `killswitch:llm` is checked first (`make llm-off` / `llm-on` /
        `llm-switch`), effective on the next request with no deploy, no TTL so it cannot
        silently re-enable itself, and falling back to `LLM_ENABLED` when the key is
        absent OR Redis is unreachable — which is the old behaviour exactly.
- ✅ I.F5 **RESOLVED 2026-09-21 (I.16).** Dense (pgvector) timed out on the first ~2
        requests after `make up`, then served the same query in 54ms — first-use work
        landing on a real user, who silently got sparse-only results and a 200 because
        retrieval degrades rather than fails. `PgvectorIndex.warm()` now runs one
        throwaway nearest-neighbour query during lifespan, so readiness goes green only
        once the first real query would succeed. No OpenAI call; unit vector rather than
        zero, since cosine distance against zero is undefined in pgvector.
- ✅ I.F6 **RESOLVED 2026-09-20 (I.14).** The out-of-corpus refusal flipped between
        runs — 9 refused / 3 answered over 12 — and the cause was NOT sampling
        (temperature is 0.0 everywhere) or a flaky guardrail. It was a **perfect 12/12
        split by which tier served**: Groq's gpt-oss-20b refused 9/9, the gpt-4o-mini
        fallback answered 3/3, and those 3 were exactly the runs where Groq raised a
        tool-binding error (I.F9). A 1-in-220 (0.45%) coincidence if the model did not
        matter. Two models, two refusal policies, one silent fallthrough.
        **Fixed by taking the decision away from the LLM** — a title-existence lookup
        before generation, plus a calibrated confidence floor for genuinely out-of-scope
        input. Both are deterministic, so the answer is now identical whichever tier
        serves. Neither behaviour was ever fabrication (gpt-4o-mini returned REAL
        in-corpus titles, so `no fabrication of absent titles` correctly passed); the
        defect was the inconsistency, and that nothing in the response revealed it.
- ✅ I.F7 **RESOLVED 2026-09-21.** A histogram with no `View` silently inherits OTel's
        MILLISECOND defaults — invisible in review and on the dashboard, which renders a
        confident line. It shipped twice: `anime.retrieval.confidence` (O.4) and both I.9
        instruments, the latter reporting a p95 of 9.5s for a stage whose entire
        wall-clock is 2.4s. Fixed in-change, and now **the guard itself is proven able to
        fail**: the check is extracted so a synthetic source with an unviewed histogram
        can be fed to it, and `test_the_view_guard_can_actually_fail` asserts it reports
        exactly that instrument (and stays quiet when everything is covered). Without
        that control the guard was only known to agree with today's code — the same
        reasoning the inspection's `--selftest` applies to its own assertions.
- ✅ I.F8 **RESOLVED 2026-09-20 (I.12).** SGLang served but published nothing:
        `sglang.launch_server` ran without `--enable-metrics`, so `/metrics` returned 404
        while `/v1/models` returned 200 with the right model. That single omission caused
        three FAILs (`engine identity`, `engines mutually exclusive`,
        `Prometheus targets 12/13`) and blanked the entire Engine-internals dashboard row.
        vLLM serves /metrics by default, which is why it only ever failed under SGLang.
        **Second defect found while verifying the first:** the check searched for a metric
        prefix Prometheus never stores for SGLang (`sglang:` vs the escaped `sglang_`), so
        it was unpassable regardless of the engine. Both fixed; 13/13 targets.
- ✅ I.F9 **RESOLVED 2026-09-21 (I.17).** gpt-oss-20b intermittently emits its tool call
        under the OpenAI `functions.` namespace prefix, which LangChain rejects even
        though the tool is registered. Severity had already been corrected down in I.13
        (2 of 3 sampled errors were 429s I caused myself), and I.14 removed the SAFETY
        consequence entirely — refusal is decided in code now, so it no longer matters
        which tier answers. What remained was pure cost and latency, and that is what is
        fixed: one immediate re-ask of the same tier on a parse error, which at p95 1.28s
        beats the 4.90s fallback it avoids on both. Never retries a 429 or a timeout.
- ✅ I.F10 **ACCEPTED 2026-09-21 (I.17) — measured, root-caused, and deliberately NOT
        "fixed" here.** The venue owns the p95 NFR breach: Qwen on SGLang p95 **10.0s**
        against Groq's **1.4s**. The obvious lever is an output-token cap, and the
        measurement rules it out:
          TTFT mean **6.44s** of an e2e mean **8.24s** -> **78% is time-to-first-token**
          inter-token latency mean **0.014s** -> decode is HEALTHY (~1.8s for a full answer)
          prefix cache hit rate **0.0** -> no reuse at all
        Capping output would touch only the ~1.8s decode portion and leave the 6.4s
        prefill untouched. This is prefill/queue-bound on a 12GB RTX 3060 that is also
        running everything else, and it is very likely worsened by I.F11. The real levers
        are smaller prompts, a warm prefix cache, or not sharing a box with the engine —
        i.e. the GPU node pool in Phases 8/9, which is where this belongs. Shipping an
        output cap now would be visible motion with no measurable effect.
- ✅ I.F11 **ACCEPTED 2026-09-21 (I.17) — same class as I.F10, and the impact boundary
        is measured.** SGLang holds a full CPU core at complete idle (99.82 / 99.63 /
        101.18% across three no-traffic samples, against `anime-api` at 0.22%) — a
        scheduler poll loop, not work. Impact, from the loop-lag metric added in I.9:
        event-loop p99 **103.4ms under battery load** against **2.2ms idle**, and rerank
        compute p95 0.998s -> 1.300s from contention alone. So it only bites when the app
        is busy at the same time — which is exactly when it matters.
        Not fixed, deliberately: the available mitigation here is a CPU limit on the
        engine container, and I.F10 shows the engine is ALREADY the latency bottleneck at
        TTFT 6.44s. Throttling it further would trade a measured 100ms of app lag for
        more of a measured 6.4s of engine lag. The correct fix is separation — the engine
        on its own node — which is Phase 8/9 work, not a local docker flag.
        Worth noting the interaction with I.11: at the old `max_length=512` this
        contention would have pushed rerank back over its timeout; at 256 it absorbed the
        hit and still passed at 65% of budget.

## TRACK D: You
- ✅ D.1 HF token
- ✅ D.2 weights
- ⏳ D.3 DigitalOcean credit
- ⏳ D.4 AWS quota
- ✅ D.5 kind + kubeconform
- ⏳ D.6 Docker Hub repo
- ✅ D.7 Clerk JWT
- ✅ D.8 medbot/voyantra auto-start (resolved — clusters removed)

---
Track L (local stack lifecycle), findings, gates and decision notes: `update_todos2.md`
