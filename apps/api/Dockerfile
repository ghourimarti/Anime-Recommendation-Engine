# syntax=docker/dockerfile:1.7
# ── Anime Recommender API — multi-stage uv build ────────────────────────────
# Build context = REPO ROOT (the API needs packages/*, migrations/, alembic.ini).
#   docker build -f apps/api/Dockerfile -t anime-api .
#
# Two stages:
#   builder  — resolves /app/.venv from the uv.lock (CPU torch, no dev deps)
#   runtime  — copies just the venv + source; non-root; healthcheck; uvicorn
#
# Both stages share the SAME uv base image so the venv's interpreter path is
# identical across stages — copying a venv between images with different python
# locations is the classic "venv is broken in the runtime image" trap.

# BASE IMAGE: the authoritative pin lives in base-images.lock at the repo root,
# which CI, the Makefile and docker-compose all inject as a build-arg. The tag
# below is a readable FALLBACK for a bare `docker build` — it is NOT pinned, so
# an image built without the build-arg is not the reproducible artifact we sign.
ARG UV_IMAGE=ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM ${UV_IMAGE} AS builder

# UV_TORCH_BACKEND=cpu is the load-bearing line: sentence-transformers (via
# anime-retrieval) pulls torch, and the Linux default is the ~2GB CUDA wheel.
# We have no GPU and the reranker runs on CPU, so pin the CPU
# wheel — saves ~1.8GB of nvidia-* libraries that would never execute.
ENV UV_TORCH_BACKEND=cpu \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# --- Layer 1 (cached unless manifests/lock change): third-party deps incl. torch
# Copy ONLY the manifests first so the expensive `uv sync` layer (torch!) is
# reused across source-only changes. uv needs every workspace member's
# pyproject.toml present to resolve, even with --package.
COPY pyproject.toml uv.lock README.md ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/retrieval/pyproject.toml packages/retrieval/pyproject.toml
COPY packages/ingestion/pyproject.toml packages/ingestion/pyproject.toml
COPY packages/eval/pyproject.toml packages/eval/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package anime-api --no-install-workspace

# --- Layer 2: workspace source + the workspace packages themselves (editable)
COPY packages/ packages/
COPY apps/api/ apps/api/
COPY migrations/ migrations/
COPY alembic.ini alembic.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package anime-api

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM ${UV_IMAGE} AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # The cross-encoder reranker downloads its model from HuggingFace on first
    # use. The non-root `app` user has no home dir (--no-create-home), so HF's
    # default cache (~/.cache = /home/app) is unwritable → the download fails and
    # retrieval silently drops the reranker every request. Point all HF caches at
    # a writable dir under the app tree (created + chowned below).
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_CACHE=/app/.cache/huggingface/hub \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers

# Non-root user — required for K8s "restricted" PodSecurity and a
# smaller CVE blast radius. UID 10001 is well outside the host's user range.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# The venv's .pth files reference /app/packages/*/src — so the source must live
# at the SAME path in runtime as it did in the builder. Copy /app wholesale
# (venv + source + manifests), owned by the non-root user.
COPY --from=builder --chown=app:app /app /app

# Writable HF/model cache for the non-root user (see HF_HOME above).
RUN mkdir -p /app/.cache/huggingface/hub /app/.cache/sentence-transformers

# Bake the cross-encoder reranker into the image at build time. Left to download
# lazily on first request, it never finishes inside the 2s RERANK_TIMEOUT and
# retrieval permanently degrades to hybrid order. Baking it makes .score() load
# from local disk — no network, no timeout, works offline.
#
# Setting RERANKER_MODEL as an ENV from the same ARG is load-bearing: the runtime
# model and the baked weights can no longer drift apart. If you override the ARG,
# the override is what gets downloaded AND what gets loaded.
#
# Model choice: ms-marco-MiniLM-L-12-v2 (33M params), ~0.63s warm on 20 real
# ~1k-char candidates. The previous default, bge-reranker-v2-m3 (568M), took
# ~6.5s — 3x over RERANK_TIMEOUT — so it timed out on EVERY request and the
# advanced-RAG lift over naive measured +0.000. L-12 reproduces the frozen eval
# baseline exactly at 3x headroom; see the table in reranker.py for the
# latency-vs-quality measurements behind this pick.
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2
ENV RERANKER_MODEL=${RERANKER_MODEL}
RUN python -c "import os;from sentence_transformers import CrossEncoder;CrossEncoder(os.environ['RERANKER_MODEL'])"

# Hand the whole cache (venv models included) to the non-root app user.
RUN chown -R app:app /app/.cache

USER app

EXPOSE 8000

# Liveness: hit /health with the stdlib (no curl in the image). Exit 1 on failure.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status==200 else sys.exit(1)"

CMD ["uvicorn", "anime_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
