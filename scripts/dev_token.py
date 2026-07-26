#!/usr/bin/env python
"""Mint a real Clerk session JWT for local verification.

The API verifies bearer tokens against Clerk's JWKS (auth fails closed), so
smoke tests, chaos scripts and load probes need a genuine signed token — there
is no bypass, by design. This mints one via the Clerk Backend API using
CLERK_SECRET_KEY, reusing a dedicated dev user so we don't litter the instance.

    export K6_AUTH_TOKEN=$(uv run python scripts/dev_token.py)
    bash scripts/deploy/smoke_local.sh

Clerk session tokens are short-lived (~60s); re-mint per run, don't cache.
Dev/staging only — never point this at a production Clerk instance.
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

CLERK_API = "https://api.clerk.com/v1"
# Must be a routable-looking address: Clerk rejects .local/.test TLDs with a 422.
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev-smoke@example.com")


def main() -> int:
    load_dotenv()
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret or secret.startswith("sk_test_..."):
        print("CLERK_SECRET_KEY not set in .env", file=sys.stderr)
        return 1

    h = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    with httpx.Client(base_url=CLERK_API, headers=h, timeout=30.0) as c:
        # Reuse the dev user if it exists; create it on first run.
        r = c.get("/users", params={"email_address": [DEV_USER_EMAIL], "limit": 1})
        r.raise_for_status()
        users = r.json()
        if users:
            user_id = users[0]["id"]
        else:
            r = c.post(
                "/users",
                json={
                    "email_address": [DEV_USER_EMAIL],
                    "password": os.environ.get("DEV_USER_PASSWORD", "anime-dev-pw-9174!"),
                    "skip_password_checks": True,
                },
            )
            if r.status_code >= 400:
                print(f"create user failed: {r.status_code} {r.text}", file=sys.stderr)
                return 1
            user_id = r.json()["id"]

        r = c.post("/sessions", json={"user_id": user_id})
        if r.status_code >= 400:
            print(f"create session failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        session_id = r.json()["id"]

        r = c.post(f"/sessions/{session_id}/tokens", json={"expires_in_seconds": 300})
        if r.status_code >= 400:
            print(f"mint token failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        print(r.json()["jwt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
