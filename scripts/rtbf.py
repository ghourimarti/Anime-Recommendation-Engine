"""Operator CLI for RTBF (right-to-be-forgotten).

Default is DRY-RUN. To actually delete, pass --confirm. This asymmetry
is deliberate: one typo on a `--confirm` invocation is irreversible, so
the safe default minimizes blast radius.

Examples:
    # Dry-run (default): show what WOULD be deleted; no Clerk call, no DB mutation.
    python scripts/rtbf.py --user user_xxxxxxxxxxxx

    # Live delete: Clerk-side + DB + audit row.
    python scripts/rtbf.py --user user_xxxxxxxxxxxx --confirm

    # Operator override — Clerk-side already done (e.g. via dashboard); finish DB only.
    python scripts/rtbf.py --user user_xxxxxxxxxxxx --confirm --skip-clerk

Exit codes:
    0 — success (dry-run or live).
    1 — Clerk-side delete failed.
    2 — usage error (missing args, env, etc.).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys

from anime_core.clerk import ClerkAPIError, ClerkClient
from anime_core.db.engine import session_scope
from anime_core.rtbf import delete_user
from dotenv import load_dotenv


async def _amain(args: argparse.Namespace) -> int:
    dry_run = not args.confirm

    clerk_client = None
    if not args.skip_clerk and not dry_run:
        secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
        if not secret:
            print(
                "error: CLERK_SECRET_KEY not set in environment.\n"
                "  Pass --skip-clerk if Clerk-side deletion was already done out-of-band.",
                file=sys.stderr,
            )
            return 2
        clerk_client = ClerkClient(secret_key=secret)

    try:
        async with session_scope() as session:
            summary = await delete_user(
                session,
                user_id=args.user,
                reason=args.reason,
                source="operator",
                dry_run=dry_run,
                clerk_client=clerk_client,
            )
    except ClerkAPIError as e:
        print(f"error: Clerk delete failed: {e}", file=sys.stderr)
        print("  DB rows untouched. Retry the same command after Clerk recovers.")
        return 1

    print(summary.format())
    if dry_run:
        print(
            "\nThis was a DRY-RUN — no Clerk call, no DB mutation.\n"
            "Re-run with --confirm to execute."
        )
    else:
        print(
            "\nLive RTBF complete. "
            "An audit row was written to `account_deletions` (idempotent on re-run)."
        )
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Operator CLI for RTBF / GDPR Art 17 right-to-erasure.",
    )
    parser.add_argument(
        "--user",
        required=True,
        help="Clerk user_id of the account to delete",
    )
    parser.add_argument(
        "--reason",
        default="operator-initiated",
        help="Free-form audit reason recorded in account_deletions.reason",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Execute the deletion. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--skip-clerk",
        action="store_true",
        help="Skip Clerk-side delete (use when Clerk-side was already done out-of-band).",
    )
    args = parser.parse_args()

    # Defensive: stdout to UTF-8 on Windows so summary chars render.
    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
