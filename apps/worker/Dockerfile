# syntax=docker/dockerfile:1.7
# ── Anime Recommender Worker — slim multi-stage uv build ─────────────────────
# Build context = REPO ROOT (worker needs packages/core + packages/ingestion).
#   docker build -f apps/worker/Dockerfile -t anime-worker .
#
# KEY DIFFERENCE from the API image: --package anime-worker pulls anime-core +
# anime-ingestion but NOT anime-retrieval → no sentence-transformers/torch →
# ~300MB instead of 2.2GB. The worker never reranks, so it carries no ML stack.

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

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
USER app

# No HTTP port — liveness is "the process is alive". K8s uses a process/exec
# probe; compose relies on the restart policy.
CMD ["python", "-m", "anime_worker"]
