# Runbook — Eval Gate Blocking PRs

The CI eval gate fires when a PR's RAGAS / IR metrics regress beyond the
threshold. Triage decides whether it's a real regression, a baseline staleness,
a flake, or model drift.

**DO NOT bump the baseline as a first step.** That's how a production
credibility moat becomes a decorative gate.

---

## 1. Symptoms

- PR CI shows `eval-gate / IR regression gate` failing with exit code 1.
- The sticky PR comment (header `eval-gate`) shows ❌ **REGRESSION** with
  one or more 🚫 metrics.

---

## 2. Triage — which kind of regression?

### 2a. Read the sticky comment

The markdown comment shows per-metric delta. Sample triage:

| Pattern in the comment | Likely cause | Go to |
|---|---|---|
| One metric regressed, large delta (e.g. `success@3 -0.12`) | Real regression in retrieval/prompt | §3a |
| All metrics shifted ~0.02–0.05 down | Embedding model change OR baseline stale | §3b |
| Borderline 3.0–3.5% relative drop | Flake — re-run the workflow | §3c |
| Embedding model changed banner shown | Expected from an embedding-model swap | §3d |

### 2b. Look at the PR's changed files

```bash
gh pr view <num> --json files | jq '.files[].path'
```

Files most likely to cause real regressions:
- `packages/retrieval/**` — hybrid weights, reranker, MMR
- `packages/core/src/anime_core/prompts/**` — prompt templates
- `packages/ingestion/**` — chunking, ingestion shape
- `evals/baseline.json` — the baseline itself (BUMP commits)

---

## 3. Mitigations

### 3a. Real regression (do NOT merge)

The PR's changes degraded quality beyond the 3% relative threshold. Options:

1. **Author fixes** — adjust the change so the regression is < 3%.
2. **Author justifies** — if the change is intentional (e.g. swapping in a
   smaller model for cost), the PR must include a `evals/baseline.json`
   bump explaining the tradeoff. Reviewer should sanity-check the tradeoff
   matches the PR description.
3. **Defer** — if the change is valuable but the regression is too large,
   merge it behind a feature flag and bump the baseline only when the flag
   is on by default.

### 3b. Baseline staleness

If `main`'s actual scores have drifted up since the baseline was last set
(because earlier improvements weren't accompanied by a baseline bump), every
PR will show a small "regression" against the stale baseline.

```bash
# Recompute main's scores
git checkout main
make eval
make eval-compare           # should be PASS or borderline-FAIL
make eval-promote           # bumps baseline to main's current scores
git checkout -b chore/bump-baseline
git add evals/baseline.json eval_report.json
git commit -m "chore(eval): bump baseline — main has drifted up since <date>"
# Open the PR; merge it; re-run the original PR
```

### 3c. Flake

LLM-as-judge metrics have stochastic noise (~1% variance per query). For
small golden sets (~30 queries), one query going off can shift `success@3`
by 1/30 = 3.3%. If the failing metric is right at the threshold and the
PR's changes don't plausibly cause it:

```bash
# Re-run the workflow
gh run rerun <run-id> --failed
```

If it consistently fails on re-run, it's NOT a flake — go back to §3a.

### 3d. Expected change after embedding-model swap

When the embedding model is changed (e.g. text-embedding-3-small → text-embedding-3-large),
ALL metrics shift. The sticky comment flags this explicitly with a
"Embedding model changed" warning banner.

Procedure:
1. Confirm the PR's intent: it's a deliberate embedding-model change.
2. Confirm `make ingest` was re-run (with the new model) before `make eval`.
3. Bump the baseline as part of the same PR:
   ```bash
   make eval-promote
   git add evals/baseline.json eval_report.json
   ```
4. The reviewer's job: check that the new baseline's absolute scores meet
   product quality bars, not just "is different from old baseline".

---

## 4. Common false alarms

| False alarm | What it actually is | Fix |
|---|---|---|
| `recall@3 -0.05` after a chunking change | Chunking shifted what's retrievable, recall@k metrics will shift even if quality is fine | Re-evaluate with `success@3` + manual eyeballing; bump baseline if quality holds |
| Every metric is wildly worse | The eval workflow's Postgres service container wasn't migrated | Check the workflow logs for `alembic upgrade head` |
| Threshold flapping ~3% | The 30-query golden set is too small | Expand to 100 (v1.x); for now, re-run the workflow |

---

## 5. Post-incident — improving the gate

When the gate fires on a false alarm THREE times in a month, it's broken:

- Threshold may need tuning (too tight) → review with the team.
- Golden set may need expansion (too small to be stable) → schedule a
  100-query expansion.
- Adversarial / canary queries may need to be split into a separate scorer
  → adversarial passes shouldn't gate IR metrics.

---

## 6. Design rationale

Implements the operational discipline behind:
- **Evaluation strategy** — CI gate + online sampling + A/B.
- **CI/CD pipeline** — the eval gate is one of the required checks.

Related artifacts:
- `evals/baseline.json` — the frozen metrics
- `packages/eval/src/anime_eval/compare.py` — the regression comparator
- `scripts/eval_promote.py` — the baseline-bump helper
- `.github/workflows/eval-gate.yml` — the workflow that runs the gate

---

**3 a.m. review:** 2026-06-12, Zaini — verified the §3b baseline-bump flow
runs against the actual `make eval-promote` Makefile target; §3c flake re-run
syntax (`gh run rerun --failed`) checked against current `gh` CLI. The
"DO NOT bump baseline as a first step" guidance (§1) is what protects this
gate from becoming decorative — preserve it.
