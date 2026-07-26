"""RTBF — right-to-be-forgotten / GDPR Article 17.

Transactional deletion of all user-scoped rows + audit-trail insert.
Ordering of operations is deliberate:

  1. Clerk-side identity delete FIRST (when a client is provided).
     - If Clerk fails: raise; our DB stays untouched. Operator retries.
     - If Clerk returns 404 (already gone): treat as success.
  2. DB transaction:
     a. DELETE rows from each user-scoped table.
        WHY explicit deletes (not relying on FK cascade): the schema uses
        `ondelete=SET NULL` on query_history and feedback so a Clerk-side
        Clerk delete doesn't auto-erase user PII. RTBF must explicitly
        delete the PII rows. usage_daily DOES cascade (it's owned by the
        user); we still delete it explicitly for telemetry symmetry.
     b. INSERT into account_deletions (the audit row).
        Idempotency via ON CONFLICT (user_id) DO NOTHING — re-running an
        RTBF on the same user is safe and doesn't crash.
     c. Commit.

User-scoped tables (live as of 2026-06-12, derived from `anime_core.db.models`):
    feedback        — ondelete=SET NULL on user_id; rows STAY → must DELETE
    query_history   — ondelete=SET NULL on user_id; rows STAY → must DELETE
    usage_daily     — ondelete=CASCADE on user_id; would auto-drop, but we
                      DELETE explicitly so the summary reports the count
    users           — the FK target; deleted last

The Clerk-side flow is opt-in (caller passes a ClerkClient). For local
dev or operator emergency override (`--skip-clerk`), pass None.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from anime_core.clerk import ClerkClient

logger = logging.getLogger(__name__)

# Order matters for FK integrity: children before parents.
# (feedback has FK → query_history AND users; query_history has FK → users;
# usage_daily has FK → users; users is last.)
_USER_SCOPED_DELETES: tuple[tuple[str, str], ...] = (
    ("feedback", "user_id = :uid"),
    ("query_history", "user_id = :uid"),
    ("usage_daily", "user_id = :uid"),
    ("users", "id = :uid"),
)

DeletionSource = Literal["self_service", "operator", "admin_panel"]


@dataclass(frozen=True)
class DeletionSummary:
    """What was (or would be) deleted, per table, plus the meta-state."""

    user_id: str
    dry_run: bool
    clerk_deleted: bool | None  # None = Clerk skipped (no client or dry-run)
    rows_deleted: dict[str, int] = field(default_factory=dict)
    audit_row_inserted: bool = False

    @property
    def total_rows(self) -> int:
        return sum(self.rows_deleted.values())

    def format(self) -> str:
        lines = [
            f"RTBF{'  [DRY-RUN]' if self.dry_run else ''}: user_id={self.user_id}",
            f"  Clerk-side: {self._clerk_state()}",
            f"  DB rows {'would delete' if self.dry_run else 'deleted'}:",
        ]
        for table, n in self.rows_deleted.items():
            lines.append(f"    {table:<18} {n:>5}")
        lines.append(f"  Total rows: {self.total_rows}")
        if self.dry_run:
            lines.append("  Audit row: not inserted (dry-run)")
        elif self.audit_row_inserted:
            lines.append("  Audit row: inserted into account_deletions")
        else:
            lines.append("  Audit row: already present (idempotent re-run)")
        return "\n".join(lines)

    def _clerk_state(self) -> str:
        if self.clerk_deleted is None:
            return "skipped (no client OR dry-run)"
        return "OK" if self.clerk_deleted else "FAILED"


async def delete_user(
    session: AsyncSession,
    *,
    user_id: str,
    reason: str = "user-initiated",
    source: DeletionSource = "self_service",
    dry_run: bool = False,
    clerk_client: ClerkClient | None = None,
) -> DeletionSummary:
    """Delete a user + all their PII + write the audit row.

    Args:
        session: an open AsyncSession (caller manages the broader scope;
                 this function commits its own transaction on success).
        user_id: Clerk user id (the PK of `users.id`).
        reason: free-form audit reason (e.g. "user-initiated via DELETE
                /v1/account", "operator: GDPR DSAR ticket #1234").
        source: who initiated. Constrained to known values for the audit
                row's `source` column.
        dry_run: when True, only counts what WOULD be deleted; does not
                 mutate anything (Clerk or DB).
        clerk_client: if provided AND not dry-run, Clerk-side delete is
                      issued FIRST. If absent (or dry-run), Clerk is skipped.

    Returns:
        DeletionSummary describing the (would-be) deletion.

    Raises:
        ClerkAPIError if Clerk-side delete failed (DB stays untouched).
        SQLAlchemy errors propagate from the DB layer.
    """
    # ── Step 1: Clerk-side identity delete (live runs only) ──────────
    clerk_deleted: bool | None = None
    if clerk_client is not None and not dry_run:
        clerk_deleted = await clerk_client.delete_user(user_id)
        # If we get here, Clerk-side succeeded (or 404 idempotent).
        # If Clerk raised, we never get here → DB stays untouched.

    # ── Step 2: DB deletes (count first; mutate only if not dry-run) ─
    rows_deleted: dict[str, int] = {}
    for table, where in _USER_SCOPED_DELETES:
        count_q = sa.text(f"SELECT COUNT(*) FROM {table} WHERE {where}")
        n = int((await session.execute(count_q, {"uid": user_id})).scalar() or 0)
        rows_deleted[table] = n
        if not dry_run and n > 0:
            delete_q = sa.text(f"DELETE FROM {table} WHERE {where}")
            await session.execute(delete_q, {"uid": user_id})

    # ── Step 3: Audit row (ON CONFLICT DO NOTHING for idempotency) ───
    audit_row_inserted = False
    if not dry_run:
        audit_q = sa.text(
            """
            INSERT INTO account_deletions (user_id, reason, source)
            VALUES (:uid, :reason, :source)
            ON CONFLICT (user_id) DO NOTHING
            RETURNING user_id
            """
        )
        result = await session.execute(
            audit_q, {"uid": user_id, "reason": reason, "source": source}
        )
        audit_row_inserted = result.scalar() is not None
        await session.commit()

    summary = DeletionSummary(
        user_id=user_id,
        dry_run=dry_run,
        clerk_deleted=clerk_deleted,
        rows_deleted=rows_deleted,
        audit_row_inserted=audit_row_inserted,
    )
    logger.info(
        "rtbf.complete user_id=%s dry_run=%s clerk=%s rows=%d audit_inserted=%s",
        user_id,
        dry_run,
        clerk_deleted,
        summary.total_rows,
        audit_row_inserted,
    )
    return summary
