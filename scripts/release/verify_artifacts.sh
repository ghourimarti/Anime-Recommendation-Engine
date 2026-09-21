#!/usr/bin/env bash
# scripts/release/verify_artifacts.sh — verify the PUBLISHED release artifacts as a
# consumer would, before running a single byte of them.
#
# WHY THIS EXISTS SEPARATELY FROM release.yml
# -------------------------------------------
# release.yml already runs `cosign verify` after signing. That is a weaker claim
# than it looks: the workflow verifies its own output, inside the same job, with
# the same credentials it just used to sign. It proves the signing step did not
# error. It does NOT prove that an independent party, on another machine, with no
# access to the signing identity, can establish where those bytes came from.
#
# That second claim is the whole point of signing, and until P7.2.5 nothing had
# ever tested it.
#
# WHAT A SIGNATURE DOES AND DOES NOT TELL YOU
# -------------------------------------------
# Keyless cosign signing stores no key. The workflow trades its GitHub OIDC token
# for a short-lived Fulcio certificate, signs, and the signature is recorded in
# Rekor, a public append-only transparency log. Verifying establishes:
#
#   PROVENANCE  these exact bytes were signed by THIS workflow, in THIS repo, at
#               THIS git ref. An attacker who pushes a malicious image to the
#               registry cannot forge it: they cannot mint an OIDC token for a
#               workflow they do not control.
#   INTEGRITY   the digest is bound into the signed payload, so the bytes have not
#               changed since signing.
#
# It establishes NOTHING about correctness. A correctly signed artifact can still
# be broken, stale or vulnerable — and this project has a live example: chart
# 0.1.0 verifies perfectly and predates every Phase 7 chart fix, so deploying it
# would not even boot the api. "Signed" is not "good".
#
# WHY IDENTITY AND ISSUER ARE BOTH MANDATORY
# ------------------------------------------
# `cosign verify` without --certificate-identity and --certificate-oidc-issuer
# accepts a signature from ANY identity in the transparency log. It answers "is
# this signed by someone?" instead of "is this signed by us?" — the difference
# between a gate and decoration. cosign v3 requires them for exactly this reason.
#
# The identity here is NOT this working tree's repo. Releases are published from
# ghourimarti/Anime-Recommendation-Engine, which is what the Fulcio certificate
# SAN records; verifying against this repo's name fails (see --selftest NC1).
#
# Usage:
#   bash scripts/release/verify_artifacts.sh
#   bash scripts/release/verify_artifacts.sh --selftest   # also prove it can FAIL
#
# Env (all defaulted; the Makefile passes them from its REL_* variables):
#   REL_IDENTITY, REL_OIDC_ISSUER, REL_API_IMAGE, REL_WEB_IMAGE,
#   REL_WORKER_IMAGE, REL_CHART_REF
#
# Exit codes:
#   0 — every signature and attestation verified
#   1 — at least one verification FAILED (do not run these bytes)
#   2 — cosign missing, or a self-test negative control unexpectedly PASSED

set -uo pipefail
cd "$(dirname "$0")/../.."

GHCR="ghcr.io/ghourimarti/anime-recommender"
REL_API_IMAGE="${REL_API_IMAGE:-$GHCR/api@sha256:6e5e1701ddfd57df99a2faa1bc02bedc94fc0bbc1aa52285d6f9905cc68afdbc}"
REL_WEB_IMAGE="${REL_WEB_IMAGE:-$GHCR/web@sha256:9ac358a8641d302280135664fd3c4a5c7af8088c6015b721e667ac6225d13836}"
REL_WORKER_IMAGE="${REL_WORKER_IMAGE:-$GHCR/worker@sha256:50419e92f67cb6fc77ee6de5c3ae46f431d241909cee727012d935b0cafff379}"
REL_CHART_REF="${REL_CHART_REF:-ghcr.io/ghourimarti/charts/anime-recommender:0.1.0}"
REL_IDENTITY="${REL_IDENTITY:-https://github.com/ghourimarti/Anime-Recommendation-Engine/.github/workflows/release.yml@refs/tags/v0.1.0}"
REL_OIDC_ISSUER="${REL_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"

if ! command -v cosign >/dev/null 2>&1; then
    # Deliberately exit non-zero rather than printing SKIP. A verification step
    # that passes when the verifier is absent is the decorative-gate bug: it
    # reports "verified" having checked nothing.
    echo "ERROR: cosign not installed - cannot verify provenance." >&2
    echo "  install: scoop install cosign   (or https://docs.sigstore.dev/cosign/installation/)" >&2
    exit 2
fi

FAILED=0

verify_sig() {
    local label="$1" ref="$2"
    if cosign verify "$ref" \
         --certificate-identity "$REL_IDENTITY" \
         --certificate-oidc-issuer "$REL_OIDC_ISSUER" >/dev/null 2>&1; then
        printf "  PASS  %-22s signature\n" "$label"
    else
        printf "  FAIL  %-22s signature   <-- DO NOT RUN THESE BYTES\n" "$label"
        FAILED=$((FAILED + 1))
    fi
}

verify_attestation() {
    local label="$1" ref="$2"
    if cosign verify-attestation "$ref" --type spdxjson \
         --certificate-identity "$REL_IDENTITY" \
         --certificate-oidc-issuer "$REL_OIDC_ISSUER" >/dev/null 2>&1; then
        printf "  PASS  %-22s SBOM attestation (spdxjson)\n" "$label"
    else
        printf "  FAIL  %-22s SBOM attestation\n" "$label"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== verifying published artifacts as a consumer ==="
echo "  identity: $REL_IDENTITY"
echo "  issuer  : $REL_OIDC_ISSUER"
echo

verify_sig "api"    "$REL_API_IMAGE"
verify_sig "web"    "$REL_WEB_IMAGE"
verify_sig "worker" "$REL_WORKER_IMAGE"
verify_sig "chart"  "$REL_CHART_REF"
echo
verify_attestation "api"    "$REL_API_IMAGE"
verify_attestation "web"    "$REL_WEB_IMAGE"
verify_attestation "worker" "$REL_WORKER_IMAGE"

# --selftest: prove the gate can fail. Without this the whole script could be a
# stub returning 0 and nobody would notice until it mattered.
if [[ "${1:-}" == "--selftest" ]]; then
    echo
    echo "=== self-test: these MUST fail ==="
    nc() {
        local label="$1"; shift
        if "$@" >/dev/null 2>&1; then
            printf "  BROKEN  %-38s verification PASSED when it must fail\n" "$label"
            FAILED=$((FAILED + 1))
        else
            printf "  ok      %-38s correctly rejected\n" "$label"
        fi
    }
    nc "wrong repo identity" cosign verify "$REL_API_IMAGE" \
        --certificate-identity "https://github.com/ghourimarti/P1-Video-SEO-Engine/.github/workflows/release.yml@refs/tags/v0.1.0" \
        --certificate-oidc-issuer "$REL_OIDC_ISSUER"
    nc "wrong OIDC issuer" cosign verify "$REL_API_IMAGE" \
        --certificate-identity "$REL_IDENTITY" \
        --certificate-oidc-issuer "https://accounts.google.com"
    nc "unsigned third-party image" cosign verify "alpine:3.20" \
        --certificate-identity "$REL_IDENTITY" \
        --certificate-oidc-issuer "$REL_OIDC_ISSUER"
fi

echo
if [[ "$FAILED" -ne 0 ]]; then
    echo "PROVENANCE VERIFICATION FAILED (${FAILED} problem(s))."
    echo "  Do not deploy or run these artifacts until this is understood."
    exit 1
fi
echo "All artifacts verified: signed by the release workflow, digests intact."
echo "  NOTE: this proves PROVENANCE, not correctness. Chart 0.1.0 verifies and is"
echo "        still stale (predates the Phase 7 fixes) - see docs/RELEASE.md."
exit 0
