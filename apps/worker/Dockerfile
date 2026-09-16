# syntax=docker/dockerfile:1.7
# ── Anime Recommender Worker — slim multi-stage uv build ─────────────────────
# Build context = REPO ROOT (worker needs packages/core + packages/ingestion).
#   docker build -f apps/worker/Dockerfile -t anime-worker .
#
# KEY DIFFERENCE from the API image: --package anime-worker pulls anime-core +
# anime-ingestion but NOT anime-retrieval → no sentence-transformers/torch →
# ~300MB instead of 2.2GB. The worker never reranks, so it carries no ML stack.

# BASE IMAGE: the authoritative pin lives in base-images.lock at the repo root,
# which CI, the Makefile and docker-compose all inject as a build-arg. The tag
# below is a readable FALLBACK for a bare `docker build` — it is NOT pinned, so
# an image built without the build-arg is not the reproducible artifact we sign.
ARG UV_IMAGE=ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM ${UV_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Manifests first (cached dep layer). uv needs every member's pyproject to resolve.
COPY pyproject.toml uv.lock README.md ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/retrieval/pyproject.toml packages/retrieval/pyproject.toml
COPY packages/ingestion/pyproject.toml packages/ingestion/pyproject.toml
COPY packages/eval/pyproject.toml packages/eval/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package anime-worker --no-install-workspace

# Source for the workspace members the worker actually uses.
COPY packages/core/ packages/core/
COPY packages/ingestion/ packages/ingestion/
COPY apps/worker/ apps/worker/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package anime-worker

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM ${UV_IMAGE} AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKER_QUEUE=feedback

# Security patches on top of the pinned base (P6.4 gate).
#
# The base is pinned by digest for reproducibility, but Debian publishes CVE
# fixes faster than the upstream uv image is rebuilt with them. Measured with
# the release's own Trivy policy (fixable HIGH/CRITICAL) against the newest
# available base: 20 findings in libgnutls30, openssl/libssl3, libpcre2-8-0 and
# libcap2 — every one already fixed in the Debian repo. `make base-images-refresh`
# reported no change, so waiting for upstream would block the release instead.
#
# The trade-off is explicit: the image is no longer a pure function of the base
# digest, because the apt snapshot moves. What ships is still auditable — the
# release records the built digest in release/images.lock and attaches an SBOM,
# so the exact package set of any released image is recoverable after the fact.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
USER app

# No HTTP port — liveness is "the process is alive". K8s uses a process/exec
# probe; compose relies on the restart policy.
CMD ["python", "-m", "anime_worker"]
