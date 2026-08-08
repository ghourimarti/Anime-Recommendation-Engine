# RTBF Procedure

When to invoke, how to invoke, what to verify after. Implements GDPR
Article 17 right-to-erasure across both paths: self-service (the user
calls `DELETE /v1/account` from the app) and operator (a DSAR ticket
gets paged to the back office).

**Implements:** GDPR Article 17 right-to-erasure — auth-scoped deletion and PII handling at depth.

---

## 1. When this gets invoked

| Trigger | Path | Who runs it |
|---|---|---|
| User clicks "Delete my account" in `/settings` | `DELETE /v1/account` endpoint | The user (auth required) |
| GDPR DSAR ticket received via email/legal | `scripts/rtbf.py` | Operator (back-office) |
| Spam/abuse account auto-purge | (v1.x — not yet implemented) | Cron worker |
| Court order / regulator demand | `scripts/rtbf.py --reason "regulator-demand-#NNN"` | Operator + legal sign-off |

---

## 2. What gets deleted

Per `packages/core/src/anime_core/rtbf.py`, in this order:

1. `feedback` rows where `user_id = X`
2. `query_history` rows where `user_id = X`
3. `usage_daily` rows where `user_id = X`
4. `users` row where `id = X`
5. (live only) Clerk-side identity via `DELETE /v1/users/{X}`
6. `account_deletions` row inserted with `(user_id, deleted_at, reason, source)`

Why explicit deletes for feedback + query_history: the schema uses
`ondelete=SET NULL` on those FKs (so a Clerk-side delete without RTBF
keeps the user's content even though the auth identity is gone). RTBF
must explicitly DELETE — otherwise the user's PII (the query text) stays
in the DB.

**Not deleted** (because not user-owned):
- `anime_titles` / `anime_chunks` — global corpus
- Langfuse traces — handled via Langfuse's own retention (see
  `docs/hardening/log-retention-policy.md`)
- CloudWatch logs — handled by class-based retention
- S3 backups — manual purge required (see §5)

---

## 3. Operator procedure (DSAR ticket)

```bash
# 1. Identify the user
# Clerk dashboard: search by email → user_id (format: user_xxxxxxxxxxxx)

# 2. Dry-run first (always)
uv run python scripts/rtbf.py --user user_xxxxxxxxxxxx
# Expected output:
#   RTBF [DRY-RUN]: user_id=user_xxxxxxxxxxxx
#     Clerk-side: skipped (no client OR dry-run)
#     DB rows would delete:
#       feedback             3
#       query_history        7
#       usage_daily          2
#       users                1
#     Total rows: 13
#     Audit row: not inserted (dry-run)

# 3. Sanity-check the dry-run output against the ticket.
#    - Does the user_id match the email on the ticket?
#    - Are the row counts reasonable for an active account?

# 4. Live run
uv run python scripts/rtbf.py --user user_xxxxxxxxxxxx --confirm \
    --reason "DSAR ticket #1234 — 2026-06-12"
# Expected output:
#   RTBF: user_id=user_xxxxxxxxxxxx
#     Clerk-side: OK
#     DB rows deleted:
#       feedback             3
#       ...
#     Audit row: inserted into account_deletions
#
# Live RTBF complete. An audit row was written to `account_deletions`.

# 5. Verify the audit row
docker compose exec postgres psql -U anime -d anime -c \
    "SELECT user_id, deleted_at, reason, source FROM account_deletions
     WHERE user_id = 'user_xxxxxxxxxxxx';"
# Expect: exactly 1 row.

# 6. Verify the user's data is gone
docker compose exec postgres psql -U anime -d anime -c \
    "SELECT COUNT(*) FROM users WHERE id = 'user_xxxxxxxxxxxx';
     SELECT COUNT(*) FROM query_history WHERE user_id = 'user_xxxxxxxxxxxx';"
# Expect: 0 in both rows.

# 7. (Manual) Purge from S3 backups
# AWS console → S3 → anime-backups bucket → find dumps containing user_id
# Each backup older than the RTBF date is subject to GDPR's
# "reasonable steps" obligation (Art 17(2)) — document the purge in the
# DSAR ticket. Backups within the 7-day retention window are exempt
# until they naturally roll off.

# 8. Close the DSAR ticket with:
#    - Date of erasure
#    - account_deletions audit row id
#    - Operator name (who ran the command)
```

---

## 4. Self-service procedure (user-driven)

User flow:

1. User signs in (Clerk).
2. Navigates to `/settings` → "Delete my account".
3. UI prompts confirmation (destructive action gated by re-entry).
4. UI calls `fetch('/v1/account', { method: 'DELETE' })`.
5. API authenticates the user, calls `delete_user(session, user_id=user.id, ...)`.
6. Clerk-side delete fires first; DB delete + audit row insert follow.
7. API returns 204.
8. UI clears local session and redirects to a "your account has been
   deleted" landing page.

Edge cases:
- Clerk-side delete fails (502 from the upstream): API returns 502 to
  the user with "please try again shortly." User is not signed out; no
  state changed. Retry-safe.
- User's session token expires mid-call: shouldn't happen (the token is
  validated at the start of the request). If it does: 401 → UI retries.
- User re-runs RTBF (e.g. account already deleted, somehow re-auth):
  the underlying `delete_user` is idempotent; 0 rows deleted, audit row
  already present, 204 returned.

---

## 5. Backups + RTBF (GDPR Art 17(2) "reasonable steps")

Backups age out per the retention policy:
- Local: `find backups -mtime +14 -delete` (see backup-restore-drill.md §4)
- Cloud RDS: 7-day automated backup window (RDS default)

GDPR doesn't require destroying backups immediately (that would risk
losing other tenants' data and is operationally impractical). The
"reasonable steps" standard is met by:
- Honoring deletion immediately in the LIVE database.
- Letting backups roll off naturally within the documented retention.
- Confirming in the DSAR ticket that no backup-from-which-restore-could-
  resurrect-the-data is older than the retention window AT THE TIME OF
  CLOSURE.

If a backup is restored after RTBF (e.g. disaster recovery), the
deleted user reappears. The recovery procedure must include a re-run of
RTBF for every user in `account_deletions` whose deletion predates the
restore point. This is a DR-drill item.

---

## 6. Audit row format

```sql
SELECT * FROM account_deletions LIMIT 1;
-- user_id   | deleted_at                 | reason                          | source
-- ----------+----------------------------+---------------------------------+--------------
-- user_xxx  | 2026-06-12 14:32:11.123+00 | DSAR ticket #1234 — 2026-06-12  | operator
```

- `user_id` is the PK — re-running RTBF on the same user does NOT
  duplicate the row (`ON CONFLICT DO NOTHING`).
- `deleted_at` is server-side `NOW()` — authoritative timestamp.
- `reason` is operator/user free-form — keep it informative.
- `source` is constrained to `self_service | operator | admin_panel`.

---

## 7. Cadence + history

- **RTBF events**: log each one in the table below. The
  `account_deletions` table is queryable for the same info but this
  doc gives a human-readable narrative.
- **Quarterly audit**: query `SELECT COUNT(*) FROM account_deletions
  WHERE deleted_at > NOW() - INTERVAL '90 days';` and confirm it matches
  the DSAR ticket count in the support system.

| Date | user_id (hash) | source | Ticket | Operator |
|---|---|---|---|---|
| _(no RTBF events yet)_ | — | — | — | — |

---

## 8. Design rationale

- **Auth scope** — `/v1/account` deletes ONLY the calling user.
- **PII handling + threat model** — RTBF is the compliance-driven
  counterpart to log redaction.
- **Postgres relational schema** — the explicit-delete order
  respects FK constraints.

When the schema changes (new user-scoped table), the RTBF script MUST
be updated to delete from it. The integration test (added later) will
catch this via a "no orphaned user-scoped rows" assertion.
