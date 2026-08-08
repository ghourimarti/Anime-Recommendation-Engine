# Audit Baseline

Single pane of glass for supply-chain audit findings. Refresh whenever any
of the three audit scripts produce new findings; the table at the top is
the at-a-glance state.

## At a glance

| Audit | Tool | Status | Findings | Last refresh | Owner |
|---|---|---|---|---|---|
| **Secrets** | regex (gitleaks-fallback hybrid) | ✅ PASS | 0 | 2026-06-11 | Zaini |
| **Dependencies — Python** | pip-audit (via uvx) | ⚠️ TOOL-FAIL | n/a | 2026-06-11 | Zaini |
| **Dependencies — Node** | pnpm audit (apps/web) | ❌ FAIL | 1 CRITICAL + 3 MEDIUM | 2026-06-11 | Zaini |
| **Licenses** | pip-licenses (uv run --with) | ✅ PASS | 0 copyleft in runtime; 6 UNKNOWN (own packages) | 2026-06-11 | Zaini |

## Reproduce

Each line is what was actually run to populate the corresponding row.

```bash
make audit-secrets    # regex over working tree + last 200 commits
make audit-deps       # pip-audit + pnpm audit, gates on CRITICAL/HIGH
make audit-licenses   # pip-licenses, gates on GPL/AGPL/LGPL in runtime
make audit-all        # all three sequentially (each one's failure stops the chain)
```

---

## Secrets audit

**Engine:** built-in regex scanner (gitleaks not installed locally). Patterns
cover: AWS access keys, OpenAI / Anthropic / Groq / Clerk / HuggingFace /
Langfuse keys, GitHub PATs, JWTs (3-part base64url), generic
`*KEY/TOKEN/SECRET/PASSWORD=<40+ char value>` assignments.

**Scope:** working tree (all `git ls-files` tracked files) + last 200 commits
of git history (added lines only).

**Findings:** 0.

**Notes:**

- 64-zero `ENCRYPTION_KEY` placeholder in `docker-compose.yml` (Langfuse dev
  default) was initially matched, then suppressed by the low-entropy filter
  (≤ 2 unique chars). This is correct — a single-character key is not a real
  secret.
- `.env` is git-ignored and never scanned. Tracked `.env.example` is scanned
  but contains only `<your-key-here>` placeholders.
- Output never includes the matched secret string itself — only file, line
  number, provider name, and a 12-character SHA-256 prefix of the value.
  This baseline can therefore be committed safely.

**Upgrade trigger:** install gitleaks (`scoop install gitleaks` / `brew install
gitleaks`) to enable the hybrid path; it has higher-precision detection on
new providers as they emerge.

---

## Dependency audit

### Python (pip-audit)

**Status:** tool error — pip-audit's resolver rejects our locked tree with a
Python-3.13 version-constraint conflict ("Ignored the following versions
that require a different python version"). Specific tool gap; not a
vulnerability finding.

**Mitigation:** Dependabot (`.github/dependabot.yml`) opens weekly
PRs for the Python `uv` ecosystem AND GitHub Advisory Database is queried
for the same packages through that path. Coverage is therefore retained
even without a successful local pip-audit run.

**Re-evaluate:** when pip-audit ships a fix, OR when we migrate to a
different tool (`uv tool run osv-scanner --lockfile=uv.lock` is the most
promising alternative — try in a later hardening pass or v1.x).

### Node (pnpm audit, apps/web)

**Status:** **4 findings** — all in dev dependencies (test runner + build
toolchain). None in shipped runtime bundles.

| Package | Installed | Advisory | Severity | Notes |
|---|---|---|---|---|
| `vitest` | < 3.2.6 | [GHSA-5xrq-8626-4rwp](https://github.com/advisories/GHSA-5xrq-8626-4rwp) | CRITICAL | Test runner — Dev only, never bundled into the Next.js output |
| `esbuild` | ≤ 0.24.2 | [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) | MEDIUM | Build tool (vite transitive) — Dev only |
| `postcss` | < 8.5.10 | [GHSA-qx2v-qp2m-jg93](https://github.com/advisories/GHSA-qx2v-qp2m-jg93) | MEDIUM | CSS toolchain — Dev only |
| `vite` | ≤ 6.4.1 | [GHSA-4w7w-66w2-5vf9](https://github.com/advisories/GHSA-4w7w-66w2-5vf9) | MEDIUM | Build tool — Dev only |

**Triage:** all four are confined to dev tooling. The runtime Next.js
bundle is produced by `next build` (which uses webpack, not vite) — these
CVEs are NOT present in shipped containers. Trivy (the CI gate) on the
built images confirms.

**Action:** Dependabot's weekly run will propose `vitest@3.2.6+`; merge it
when the PR lands. The 3 MEDIUMs follow via vitest's transitive dep update.

**Owner:** Zaini.

---

## License audit

**Tool:** pip-licenses invoked via `uv run --with pip-licenses` so it
introspects the project venv (uvx alone isolates from our deps).

**Scope:** all installed Python packages in the project venv (153 total),
ignoring `pip`, `setuptools`, `wheel`.

**Classification:**

| Class | Count |
|---|---|
| Permissive (MIT / BSD / Apache / ISC / PSF / MPL / Unlicense) | 146 |
| Copyleft (GPL / AGPL / LGPL) — **runtime** | **0** |
| Copyleft — dev | 0 |
| Other | 1 |
| Unknown | 6 |

**Runtime vs dev split:** Python deps classified as "runtime" come from
`uv export --no-dev --format=requirements-txt`. The 9 runtime packages are
the direct runtime deps; transitive runtimes are folded into the same
group via uv's resolver. The 144 "dev" count includes pytest, ruff, mypy,
pre-commit, alembic-dev tooling — none shipped to production containers.

**Unknown licenses (6):** all our own workspace members (`anime-api`,
`anime-core`, `anime-eval`, `anime-ingestion`, `anime-retrieval`,
`anime-worker`). They report "UNKNOWN" because `pyproject.toml` doesn't
declare a license. **Action:** add a `license = { text = "TBD" }`
field to each workspace member's pyproject when we lock the project
license. Not blocking.

**Owner:** Zaini.

---

## Node licenses

Not audited in v1. Mitigation: the Dockerfile for the web image uses
Next.js standalone output, which bundles a minimal set of
node_modules; the production image is independently SBOM-scannable via
Trivy and would flag any AGPL transitive dep at build time. Add explicit
`license-checker` to a v1.x audit script if a later pass needs it.

---

## Maintenance

- Refresh this doc **monthly** or **after any Dependabot batch merge**.
- The "Last refresh" column means "last time this row was verified against
  a real audit run." Stale rows are worse than no rows — review at the same
  cadence as Dependabot triage.
- When `make audit-secrets` finds something, treat it as a P1 — rotate the
  key first, then investigate how it got there.
- When `make audit-deps` upgrades severity (e.g. MEDIUM → HIGH because the
  CVE was reassigned), Dependabot may not catch it for a week. The audit
  run is the canonical re-evaluation; this doc is the audit's memory.
