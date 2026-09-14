## What & Why

<!-- 1-3 sentences: what does this PR change and why? -->

## Related

<!-- Link related issues/PRs, or note the motivation if this is standalone. -->

## How verified

<!-- Concrete: which tests run, which `make` target shows it works,
screenshots if UX. -->

- [ ] `make check` passes locally (ruff + mypy + pytest)
- [ ] Unit tests added/updated for new behavior
- [ ] If retrieval / prompts / eval / ingestion changed: ran `make eval` and `make eval-compare` — no regression beyond 3% relative / 0.01 absolute
- [ ] If Helm / Terraform changed: `make render-verify` (every vendor × env) + `terraform validate` clean
- [ ] If web changed: `pnpm test` + manual streaming UX smoke
- [ ] Docs / runbooks updated if behavior changes

## Risk & rollback

<!--
Reversibility: easy / moderate / hard. What breaks if rolled back?
For Helm/migration changes, name the rollback step explicitly.
-->
