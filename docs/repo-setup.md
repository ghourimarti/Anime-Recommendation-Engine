# Repo Setup — Branch Protection, Secrets, and First-Run Checklist

CI wiring: CI + eval gate + CD workflows. Some configuration lives outside
the repo (in GitHub's UI, in AWS IAM, in CI secrets) and is documented here.
Follow this once when adopting the workflows on a fresh GitHub repo.

## 1. Branch protection (`main`)

Settings → Branches → Add rule on `main`:

- **Require pull request before merging** — yes
 - Required reviewers: 1 (or 0 for solo dev — keep the affordance for later)
 - Dismiss stale reviews on push: yes
 - Require review from CODEOWNERS: yes
- **Require status checks to pass** — yes; pin these check names:
 - `ci / Python (lint + typecheck + test)`
 - `ci / Web (typecheck + lint + test + build)`
 - `ci / Build images + Trivy scan (api)`
 - `ci / Build images + Trivy scan (web)`
 - `ci / Build images + Trivy scan (worker)`
 - `eval-gate / IR regression gate` _(required only when the PR touches eval-relevant paths — GitHub correctly skips non-triggered required checks)_
- **Require branches to be up to date** — yes
- **Require linear history** — yes (squash merge only)
- **Require signed commits** — recommended once you have a signing key set up
- **Do not allow bypassing the above** — yes for everyone except repo admins

## 2. Required GitHub Secrets (Settings → Secrets and variables → Actions → Secrets)

| Secret | Used by | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | `eval-gate.yml` | Query embeddings for the golden set; ~$0.01/PR spend |

`ci.yml` and `cd.yml` do NOT consume secrets — `ci` is offline, `cd` uses OIDC.

## 3. Required GitHub Variables (Settings → Secrets and variables → Actions → Variables)

| Variable | Example | Purpose |
|---|---|---|
| `ECR_REGISTRY` | `123456789012.dkr.ecr.us-east-1.amazonaws.com` | Push target for prod images |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/anime-cd-github` | AWS role the CD workflow assumes via OIDC; created in Terraform (the Terraform IAM apply) |

## 4. AWS OIDC trust (one-time, in Terraform)

`cd.yml` uses GitHub's OIDC identity provider to assume an AWS role — no
long-lived access keys live in GitHub Secrets. The role + trust policy are
created by `infra/terraform/modules/iam` the relevant build step. The trust policy
restricts assumption to: this repo, on tag refs matching `v*.*.*` only.

Until the Terraform IAM apply has applied, `cd.yml` fails at "Assume AWS role" — that's
expected. Don't push tags before the cloud deploy.

The `tag: vX.Y.Z` regex in `cd.yml`'s `bump-helm` job assumes the Helm
`values-prod.yaml` uses literal semver tags. If you adopt sha-pinned tags or
floating channels (`stable`, `canary`), extend the regex accordingly.

## 5. Dependabot — first-week noise

The first run will open ~10–15 PRs as Dependabot catches up. Triage strategy:

- Patch updates → auto-merge after CI passes (Settings → General → "Allow auto-merge").
- Minor updates → review manually for `langchain*`, `next`, `react` (these have shipped breaking changes in minors).
- Major updates → never auto-merge.
- Python `torch` is pinned to the PyTorch CPU index in `pyproject.toml`. Any torch upgrade PR should be reviewed end-to-end.

## 6. Eval gate — operating it

- The committed baseline lives at `evals/baseline.json` (10 IR metrics).
- The gate compares each PR's freshly-generated `eval_report.json` against it.
- Threshold: relative drop > 3% **AND** absolute drop > 0.01 → blocks merge.
 (Both conditions must breach. Tiny absolute drops on small metrics don't fire.)
- `distinct_ratio` is reported but never gates.
- A sticky markdown comment is posted on each PR with the per-metric delta —
 see the live header `eval-gate`.

### When the baseline should be bumped

A PR that intentionally improves metrics also bumps the baseline:

```bash
make eval                                  # generates eval_report.json (~$0.01 OpenAI)
make eval-promote                          # copies advanced metrics -> evals/baseline.json
git add evals/baseline.json eval_report.json
git commit -m "eval: bump baseline — <reason>"
```

The reviewer should sanity-check that the baseline bump matches the PR's intent
(not a stealth regression bump).

### When the baseline does NOT need bumping

- Frontend-only changes (`apps/web/**`).
- Infra / Helm / Terraform changes (`infra/**`).
- Docs / runbook changes (`docs/**`).
- Test-only changes that don't touch retrieval logic.

The path filter in `eval-gate.yml` skips these PRs entirely — they don't pay
the OpenAI spend, and the eval-gate check is not required for their merge.

## 7. Workflow runtime budget

| Workflow | Target p95 | Notes |
|---|---|---|
| `ci.yml` Python | 8 min | uv cache warm + ruff fast |
| `ci.yml` Web | 5 min | pnpm cache + Next standalone build |
| `ci.yml` Build & scan | 12 min | parallel buildx matrix + Trivy |
| `eval-gate.yml` | 6 min | postgres warmup + ~268 anime ingest + 30-query eval |
| `cd.yml` | 8 min | parallel image build + ECR push |

If any workflow consistently exceeds 1.5× its budget, the cache is cold —
check `astral-sh/setup-uv` and `pnpm/action-setup` `cache-hit` outputs.

## 8. First-run checklist (fresh GitHub repo)

- [ ] Push the branch with these workflow files; confirm the Actions tab shows them
- [ ] Set required Secrets and Variables (§2 + §3)
- [ ] Open a no-op PR (e.g. README typo); confirm `ci.yml` runs and passes
- [ ] Open a PR touching `packages/retrieval/**`; confirm `eval-gate.yml` triggers and posts the sticky comment
- [ ] Configure branch protection (§1) referencing the exact check names from a green run
- [ ] Replace `@OWNER` in `.github/CODEOWNERS` with your GitHub handle
- [ ] Enable Dependabot in Settings → Security → Code security and analysis
- [ ] Tag a release `v0.1.0` to exercise `cd.yml` — **only after the Terraform IAM apply has applied the IAM role + ECR repos**, otherwise the workflow fails as designed

## 9. Local verification (before pushing CI changes)

The workflow files have no syntax-only validator in pre-commit (actionlint is a
separate install). Before pushing changes to `.github/workflows/*.yml`:

```bash
# install actionlint once
scoop install actionlint      # Windows
brew install actionlint       # macOS

# lint
actionlint .github/workflows/*.yml

# run the equivalent of each job locally
make check                                     # ci.yml / python job
cd apps/web && pnpm typecheck && pnpm lint && pnpm test && pnpm build
make eval && make eval-compare                 # eval-gate.yml job (needs DATABASE_URL + OPENAI_API_KEY)
```

The eval-gate cannot be fully reproduced locally without Postgres + an
OpenAI key. That's the honest CI verification ceiling — the gate's logic is
covered by `packages/eval/tests/test_compare.py` (24 tests), and the full
end-to-end run happens in GitHub Actions on every PR.
