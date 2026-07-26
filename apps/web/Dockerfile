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

# NEXT_PUBLIC_* are inlined into the client bundle at BUILD time (Next limitation),
# so the Clerk *publishable* key must be a build ARG, not a runtime env. The
# *secret* key stays a runtime env (it's server-only). Per-env prod builds
# pass the matching publishable key here.
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=""
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
# Public origin (browser-facing URL). Used for metadataBase at build time and,
# more importantly, so the auth middleware builds Clerk return URLs against a
# reachable address instead of the container's internal 0.0.0.0:3000 bind.
ARG NEXT_PUBLIC_SITE_URL=""
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}
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
