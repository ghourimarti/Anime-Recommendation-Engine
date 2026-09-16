# Update Todos (complete)

**Totals: 118 done · 40 pending · 8 in progress · 0 blocked · 6 phases complete (0–5)**

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

## PHASE 6: Release Packaging 🔄 4/12
- ✅ P6.1 base-images.lock
  - ✅ P6.1a stdin bug under make
- 🔄 P6.2 dual registry
  - 🔄 P6.2.1 ghcr.io (PAT)
  - 🔄 P6.2.2 Docker Hub mirror
- 🔄 P6.3 tagging
- 🔄 P6.4 SBOM + Trivy
- 🔄 P6.5 cosign keyless
- 🔄 P6.6 OCI chart
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
- ⏳ P6.10 consumption proof on kind

## PHASE 7: Local & kind 🔄 2/6
- ✅ P7.1 images
- ✅ P7.2 compose e2e
  - ✅ P7.2.1 smoke script
  - ✅ P7.2.2 stage1 doc
  - ✅ P7.2.3 make targets
  - ✅ P7.2.4 acceptance run
  - ⏳ P7.2.5 re-verify with registry images
- 🔄 P7.3 kind + Helm
  - ✅ P7.3.1 values-local (delivered by P6.7)
  - ⏳ P7.3.2 up script
  - ⏳ P7.3.3 down script
  - ⏳ P7.3.4 smoke
  - ⏳ P7.3.5 stage2 doc
  - ⏳ P7.3.6 make targets
  - ✅ P7.3.7 kubeconform (delivered by P6.9)
- ⏳ P7.4 probes / HPA / DNS
- ⏳ P7.5 failure drills
- ⏳ P7.6 terraform plan

## PHASE 8: Managed K8s (DOKS) ⏳ 0/12
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

## PHASE 9: AWS EKS ⏳ 0/9
- ⏳ P9.1 account + quota
- ⏳ P9.2 VPC + EKS
- ⏳ P9.3 IRSA
- ⏳ P9.4 RDS / ElastiCache / SQS / ESO
- ⏳ P9.5 same digests, config-only diff
- ⏳ P9.6 GPU nodes
- ⏳ P9.7 ArgoCD + canary rehearsal
- ⏳ P9.8 cost comparison
- ⏳ P9.9 findings

## PHASE 10: Portfolio ⏳ 0/6
- ⏳ P10.1 diagram
- ⏳ P10.2 README
- ⏳ P10.3 metrics story
- ⏳ P10.4 findings
- ⏳ P10.5 demo
- ⏳ P10.6 talking points

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
