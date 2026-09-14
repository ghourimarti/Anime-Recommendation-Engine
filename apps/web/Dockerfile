# syntax=docker/dockerfile:1.7
# ── Anime Recommender Web (Next.js) — multi-stage standalone build ─────────────
# Build context = apps/web (self-contained pnpm project).
#   docker build -f apps/web/Dockerfile -t anime-web apps/web
#
# Three stages:
#   deps     — `pnpm install --frozen-lockfile` (cached unless lockfile changes)
#   builder  — `pnpm build` → .next/standalone (Next traces the minimal file set)
#   runtime  — node:22-alpine, non-root, copy standalone output, `node server.js`
#
# `output: "standalone"` in next.config.mjs is what makes the runtime image ~120MB
# instead of ~1GB — Next copies only the traced node_modules, not all of them.

# BASE IMAGE: the authoritative pin lives in base-images.lock at the repo root,
# which CI, the Makefile and docker-compose all inject as a build-arg. The tag
# below is a readable FALLBACK for a bare `docker build` — it is NOT pinned, so
# an image built without the build-arg is not the reproducible artifact we sign.
ARG NODE_IMAGE=node:22-alpine

# ─── Stage 1: deps ───────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
# corepack ships with node 22 and pins the pnpm version from package.json.
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && pnpm install --frozen-lockfile

# ─── Stage 2: builder ────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# The Clerk publishable key and the public site URL are NOT build inputs: the app
# reads CLERK_PUBLISHABLE_KEY and SITE_URL from the container environment per
# request (src/lib/runtime-config.ts). Baking them in tied every image to one
# Clerk instance and one hostname, breaking build once, deploy many (Phase 6, R2).
# Billing checkout stub flag (UI redesign 3D). Build-time like all NEXT_PUBLIC_*;
# keep "false" until a payment provider is integrated (needs explicit approval).
ARG NEXT_PUBLIC_BILLING_ENABLED="false"
ENV NEXT_PUBLIC_BILLING_ENABLED=${NEXT_PUBLIC_BILLING_ENABLED}
# Telemetry off in CI/builds.
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && pnpm build

# ─── Stage 3: runtime ────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# node:alpine ships a built-in non-root `node` user (UID 1000) — use it.
# standalone output bundles a minimal server.js + the traced node_modules.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000

# Liveness: the Next server answers on / even pre-auth (middleware 307-redirects,
# which is still a healthy 3xx response, not a connection failure).
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
