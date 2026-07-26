# syntax=docker/dockerfile:1.7
# ─── Custom k6 binary with xk6-sse — for streaming-endpoint load tests ───────
# Stock k6 has no SSE client. We need the `k6/x/sse` module from xk6-sse to
# load-test /v1/recommend/stream.
#
# Build:    docker build -t k6-sse:latest tests/load/k6/xk6
# Run:      docker run --rm -i --network host \
#             -e BASE_URL=http://localhost:1005 \
#             -e K6_AUTH_TOKEN=$TOKEN \
#             -v $(pwd)/tests/load:/load \
#             k6-sse:latest run /load/k6/stream_sustained_30rps.js
#
# (Linux/macOS uses --network host. On Windows + Docker Desktop, replace
# localhost with host.docker.internal — see tests/load/README.md §4.)
#
# Alt: build the binary locally if you have Go installed:
#   go install go.k6.io/xk6/cmd/xk6@latest
#   xk6 build --with github.com/phymbert/xk6-sse@latest
#   ./k6 run tests/load/k6/stream_sustained_30rps.js

ARG GO_VERSION=1.23
ARG ALPINE_VERSION=3.20

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM golang:${GO_VERSION}-alpine AS builder

ENV CGO_ENABLED=0 \
    GOOS=linux \
    GO111MODULE=on

RUN apk add --no-cache git ca-certificates

WORKDIR /build

# Pinned versions deliberately — xk6 and xk6-sse have shipped breaking
# changes; pin and let dependabot propose bumps.
ARG XK6_VERSION=v0.13.0
ARG XK6_SSE_VERSION=v0.1.6

RUN go install go.k6.io/xk6/cmd/xk6@${XK6_VERSION} \
 && xk6 build --output /build/k6 \
        --with github.com/phymbert/xk6-sse@${XK6_SSE_VERSION}

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM alpine:${ALPINE_VERSION} AS runtime

RUN apk add --no-cache ca-certificates \
 && addgroup -g 10001 k6 \
 && adduser -D -u 10001 -G k6 -s /sbin/nologin k6

COPY --from=builder /build/k6 /usr/local/bin/k6
RUN chmod +x /usr/local/bin/k6

USER k6
WORKDIR /load

# Sanity at build time: print the binary's available modules. If `k6/x/sse`
# isn't there, the build is broken and we fail loudly.
RUN k6 version

ENTRYPOINT ["k6"]
CMD ["--help"]
