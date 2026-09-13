#!/usr/bin/env bash
# scripts/release/refresh_base_images.sh — re-resolve base image tags to digests (P6.1).
#
# Reads the TAG portion of each entry in base-images.lock, asks the registry what
# digest that tag currently points at, and rewrites the lock. Prints a diff-style
# summary so the bump is reviewable rather than a silent 64-hex-character change.
#
# A base-image bump is a supply-chain event: new upstream packages, new CVEs, a
# new Trivy result. Run this on its own, review, and commit it as its own change
# — never let it ride along in a feature PR where nobody will look at it.
#
# Usage:
#   bash scripts/release/refresh_base_images.sh            # rewrite the lock
#   bash scripts/release/refresh_base_images.sh --check    # CI mode: fail if stale
#
# Exit codes:
#   0 — lock is current (--check), or was rewritten
#   1 — lock is stale (--check only)
#   2 — a tag could not be resolved

set -euo pipefail

cd "$(dirname "$0")/../.."
LOCK=base-images.lock
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

[[ -f "$LOCK" ]] || { echo "FAIL  $LOCK not found" >&2; exit 2; }

changed=0
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

while IFS= read -r line; do
    # Pass comments and blanks through untouched.
    if [[ -z "$line" || "$line" == \#* ]]; then
        printf '%s\n' "$line" >> "$tmp"
        continue
    fi

    key=${line%%=*}
    ref=${line#*=}
    tag=${ref%%@*}          # strip any existing @sha256:...
    old_digest=${ref#*@}
    [[ "$old_digest" == "$ref" ]] && old_digest="(unpinned)"

    # `< /dev/null` is load-bearing. Without it docker inherits — and consumes —
    # the while-loop's stdin, so the loop sees EOF after the first entry. It
    # works interactively (stdin is a TTY) and fails under make/CI, which is
    # precisely where this gate is supposed to run. Classic read-loop footgun.
    new_digest=$(docker buildx imagetools inspect "$tag" 2>/dev/null < /dev/null \
        | awk '/^Digest:/ {print $2; exit}')

    if [[ -z "$new_digest" ]]; then
        echo "FAIL  could not resolve $tag" >&2
        exit 2
    fi

    printf '%s=%s@%s\n' "$key" "$tag" "$new_digest" >> "$tmp"

    if [[ "$old_digest" == "$new_digest" ]]; then
        printf '  %-12s unchanged  %s\n' "$key" "${new_digest:0:19}…"
    else
        changed=1
        printf '  %-12s CHANGED\n' "$key"
        printf '      was  %s\n' "$old_digest"
        printf '      now  %s\n' "$new_digest"
    fi
done < "$LOCK"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
    if [[ "$changed" -eq 1 ]]; then
        echo
        echo "FAIL  base-images.lock is stale — run: make base-images-refresh" >&2
        exit 1
    fi
    echo
    echo "  lock is current."
    exit 0
fi

if [[ "$changed" -eq 1 ]]; then
    # Keep the "Last refreshed" line honest — a lock that claims a date it does
    # not have is worse than no date.
    sed -i "s|^# Last refreshed: .*|# Last refreshed: $(date -u +%Y-%m-%d)|" "$tmp"
    mv "$tmp" "$LOCK"
    trap - EXIT
    echo
    echo "  $LOCK updated. Review the diff, then commit it ALONE:"
    echo "      git add base-images.lock"
    echo "      git commit -m 'build: bump base image digests'"
else
    echo
    echo "  no changes — $LOCK already current."
fi
