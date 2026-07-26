# Load Tests

k6-based load harness for the anime-recommender API. Validates the
non-functional requirements (latency, throughput, error rate) against the
running stack.

## 1. Install k6

Choose your platform:

```bash
# Windows (Scoop)
scoop install k6

# Windows (winget)
winget install k6.k6 --source winget

# macOS
brew install k6

# Debian/Ubuntu
sudo gpg -k && sudo gpg --no-default-keyring \
    --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
    --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/k6.list
sudo apt update && sudo apt install k6
```

Verify: `k6 version` should print v0.50+.

The **streaming** scenario needs a custom k6 binary — see §4.

## 2. Mint a Clerk dev-tenant JWT (one-time)

The harness uses the **real** auth code path (no test
bypass that could drift from prod). Mint a JWT from your Clerk dev tenant
and export it as `K6_AUTH_TOKEN`.

### Option A — Clerk Dashboard

1. Sign in at https://dashboard.clerk.com → your dev project.
2. Create a test user (`loadtest@example.com`).
3. Sessions → Generate session token (long-lived for tests).
4. Copy the JWT.

### Option B — `@clerk/clerk-sdk-node` programmatic mint

```bash
# In apps/web (Clerk SDK already installed there)
pnpm node -e "
  const { clerkClient } = require('@clerk/clerk-sdk-node');
  (async () => {
    const session = await clerkClient.sessions.createSession({
      userId: process.env.CLERK_TEST_USER_ID,
    });
    const token = await clerkClient.sessions.getToken(session.id, 'default');
    console.log(token.jwt);
  })();
"
```

### Export & rotate

```bash
export K6_AUTH_TOKEN="eyJhbGciOi..."
```

Rotate the token every ~7 days. The smoke test catches an expired token in
~5 seconds (all `/v1/recommend` requests 401).

## 3. Bring the stack up

The load test hits a real API process backed by Postgres + Redis + the LLM
provider. Two patterns:

### Pattern A — single API process + compose stack

```bash
docker compose up -d postgres redis
make db-migrate
make ingest
make dev-api      # in another terminal — runs uvicorn on :8000
```

### Pattern B — fully containerised

```bash
docker compose up -d
# API auto-runs at :8000 inside the compose network
```

Sanity check before running k6:
```bash
curl -i http://localhost:8000/health   # 200 ok
curl -i http://localhost:8000/ready    # 200 ready
```

## 4. Run a scenario

```bash
export BASE_URL=http://localhost:8000
export K6_AUTH_TOKEN="..."

# Smoke (always run first)
k6 run tests/load/k6/smoke.js

# Sustained NFR gate
k6 run --summary-export=tests/load/reports/sustained_50rps_$(date +%s).json \
       tests/load/k6/sustained_50rps.js

# Peak burst
k6 run --summary-export=tests/load/reports/peak_200rps_$(date +%s).json \
       tests/load/k6/peak_200rps.js

# Diagnostic ramp (no thresholds)
k6 run --summary-export=tests/load/reports/ramp_$(date +%s).json \
       tests/load/k6/ramp_to_knee.js
```

Make targets exist for each (see `make help`).

## 5. Streaming scenario (xk6-sse — custom k6 build required)

Stock k6 has no SSE client. The streaming scenario imports `k6/x/sse` from
[phymbert/xk6-sse](https://github.com/phymbert/xk6-sse) and needs a binary
built with that extension. Two ways:

### Path A — Docker (recommended; no Go install needed)

```bash
# Build the custom image once
docker build -t k6-sse:latest tests/load/k6/xk6

# Run a streaming scenario
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000 \
  -e K6_AUTH_TOKEN=$K6_AUTH_TOKEN \
  -v $(pwd)/tests/load:/load \
  k6-sse:latest run /load/k6/stream_sustained_30rps.js
```

**Windows + Docker Desktop:** replace `--network host` with `--network bridge`
and `BASE_URL=http://localhost:8000` with `BASE_URL=http://host.docker.internal:8000`.

### Path B — local Go build (if Go is installed)

```bash
go install go.k6.io/xk6/cmd/xk6@latest
xk6 build --with github.com/phymbert/xk6-sse@latest
./k6 run -e BASE_URL=http://localhost:8000 -e K6_AUTH_TOKEN=$K6_AUTH_TOKEN \
         tests/load/k6/stream_sustained_30rps.js
```

The resulting `./k6` binary works for ALL scenarios (it's a superset of
stock k6) — convenient if you don't want both binaries on PATH.

## 6. Reading the output

Each scenario writes a `tests/load/reports/<scenario>-<unixtime>.json` when
run with `--summary-export`. k6's stdout shows the threshold pass/fail summary
and the metric percentiles for the run.

```bash
# Quick percentile peek for the most recent sustained run
ls -1 tests/load/reports/sustained_50rps_*.json | tail -1 | xargs jq '.metrics | with_entries(select(.key | startswith("http_req_duration") or startswith("anime_")))'
```

For scenario-specific interpretation + the tuning playbook, see
[scenarios.md](scenarios.md).

## 7. CI

Load tests are **not** wired into the CI eval gate. They take 5–10
min each, would cost real OpenAI spend on every PR, and depend on a running
stack. The k6 scripts are syntax-checked by `node --check` in `make
load-validate`; full runs are operator-triggered (or part of staging
validation).

## 8. Verification ceiling (honest)

A passing sustained_50rps run on a single-replica local docker-compose stack
demonstrates the **patterns** hold at synthetic 50 RPS. It does NOT prove:

- Production at 100k MAU is operationally healthy (needs real users + on-call).
- Long-tail failures (cache stampede, single-tenant runaway, 11-day leak).
- Multi-region latency (single-region only in v1).

Synthetic load demonstrates the architecture and patterns; operating at real
production scale is a separate concern this repo does not claim to prove.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every request 401 | `K6_AUTH_TOKEN` missing/expired | Re-mint per §2 |
| Connection refused | API not up | `make dev-api` or `docker compose up` |
| 503 on `/ready` | DB / Redis down | `docker compose up postgres redis` |
| sustained p95 wildly off | Cold caches | Run smoke first to warm them; sustained measures warm-state |
| streaming scenario "module not found: k6/x/sse" | Stock k6 binary | Build custom k6 per §5 |
| `anime_server_work_ms` shows no data | Stock route bypassed the timer wrap | Confirm the route still calls `time_server_work()` around `service.recommend()` |
