#!/usr/bin/env bash
# scripts/release/mirror_image.sh — copy a locally cached image into a PRIVATE
# ghcr.io package and print the reference to pin by digest (Track L, O2).
#
# Why this exists: `minio/minio` and `minio/mc` no longer pull from Docker Hub
# ("repository does not exist"), and the observability tier needs MinIO. The
# copy cached on this machine still runs and ships `mc`, so it is pushed to a
# private package and compose pins it by DIGEST: identical bytes on every
# machine, and nobody can move a tag underneath us.
#
# Private on purpose: MinIO is AGPL-3.0. Running it internally is fine; a PUBLIC
# copy is redistribution, with source-offer obligations. Packages pushed from a
# user account start private — keep this one that way.
#
# Only the local platform is pushed (--platform). The cached image is a single
# platform, while its Docker Hub index listed several; pushing the whole index
# fails on the layers that were never downloaded.
#
# An existing tag is never overwritten — its current digest is printed instead.
#
# Prerequisite, once per machine (needs the write:packages scope):
#   gh auth refresh -h github.com -s write:packages,read:packages
#   gh auth token | docker login ghcr.io -u ghourimarti --password-stdin
#
# Usage:  bash scripts/release/mirror_image.sh <local-image> <ghcr-repo> <tag>
#   e.g.  bash scripts/release/mirror_image.sh minio/minio:latest \
#             ghcr.io/ghourimarti/minio RELEASE.2025-09-07T16-13-09Z
# Output: last line is the pinned reference  <ghcr-repo>:<tag>@sha256:...
# Exit:   0 pinned reference printed · 1 push/inspect failed · 2 usage

set -euo pipefail

if [[ $# -ne 3 ]]; then
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
    exit 2
fi
SRC=$1
REPO=$2
TAG=$3
DEST="$REPO:$TAG"

if ! docker image inspect "$SRC" >/dev/null 2>&1; then
    echo "FAIL  $SRC is not cached on this machine" >&2
    exit 1
fi
PLATFORM=$(docker image inspect "$SRC" --format '{{.Os}}/{{.Architecture}}')

if docker buildx imagetools inspect "$DEST" >/dev/null 2>&1 </dev/null; then
    echo "  $DEST already exists — not overwriting; pinning its current digest"
else
    echo "  pushing $SRC → $DEST ($PLATFORM only)"
    docker tag "$SRC" "$DEST"
    docker push --platform "$PLATFORM" "$DEST"
fi

DIGEST=$(docker buildx imagetools inspect "$DEST" </dev/null | awk '/^Digest:/ {print $2; exit}')
if [[ -z "$DIGEST" ]]; then
    echo "FAIL  pushed, but could not read the digest of $DEST" >&2
    exit 1
fi
echo "$DEST@$DIGEST"
