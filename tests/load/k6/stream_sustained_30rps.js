// Streaming sustained 30 RPS for 3 min — SSE TTFT validation.
//
// REQUIRES the custom k6 binary built from tests/load/k6/xk6/Dockerfile (or
// via `xk6 build --with github.com/phymbert/xk6-sse@latest`). See
// tests/load/README.md §4 for the build procedure. The stock `k6` binary
// does NOT include the `k6/x/sse` module and this script will fail at
// import time with that one.
//
// Why 30 RPS (not 50): streaming responses hold the connection open for the
// duration of the LLM generation (~3-8s in our budget). At 50 RPS x 5s mean
// duration = 250 concurrent connections — fine for the architecture, but
// triple the smoke-able local stack. 30 RPS is the comfortable "demonstrate
// the pattern works" rate for local docker-compose.
//
// NFR mapping:
//   - anime_sse_ttft_ms p50 < 800    (TTFT p50 NFR)
//   - anime_sse_ttft_ms p95 < 2500   (TTFT p95 NFR)
//   - anime_sse_ttft_ms p99 < 5000   (TTFT p99 NFR)
//   - anime_sse_total_ms p95 < 8000  (full response p95 NFR)
//
// Run (custom k6 binary required):
//   ./k6-sse run -e BASE_URL=http://localhost:1005 -e K6_AUTH_TOKEN=$TOKEN \
//                --summary-export=tests/load/reports/stream_$(date +%s).json \
//                tests/load/k6/stream_sustained_30rps.js

// eslint-disable-next-line import/no-unresolved
import sse from 'k6/x/sse';
import { check } from 'k6';
import { authHeaders } from './lib/auth.js';
import { pickQuery } from './lib/queries.js';
import {
  sseTtftMs,
  sseTotalMs,
  sseEventsPerStream,
  sseConnectErrors,
} from './lib/metrics.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1005';

export const options = {
  scenarios: {
    stream: {
      executor: 'constant-arrival-rate',
      rate: 30,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 200,
      maxVUs: 400,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    anime_sse_ttft_ms: [
      'p(50)<800',
      'p(95)<2500',
      'p(99)<5000',
    ],
    anime_sse_total_ms: [
      'p(95)<8000',
    ],
    anime_sse_connect_errors: ['count<10'],   // <10 hard failures across the whole run
  },
};

export default function () {
  const url = `${BASE_URL}/v1/recommend/stream`;
  const body = JSON.stringify({ query: pickQuery() });
  const params = {
    method: 'POST',
    body,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...authHeaders(),
    },
    tags: { name: 'recommend_stream' },
  };

  const startedAtMs = Date.now();
  let firstEventAtMs = null;
  let eventCount = 0;
  let sawDone = false;

  const response = sse.open(url, params, function (client) {
    client.on('event', function (event) {
      if (firstEventAtMs === null) {
        firstEventAtMs = Date.now();
        sseTtftMs.add(firstEventAtMs - startedAtMs);
      }
      eventCount += 1;
      if (event.name === 'done' || (event.data && event.data.indexOf('[DONE]') !== -1)) {
        sawDone = true;
        client.close();
      }
    });
    client.on('error', function () {
      sseConnectErrors.add(1);
      client.close();
    });
  });

  const endedAtMs = Date.now();
  if (firstEventAtMs !== null) {
    sseTotalMs.add(endedAtMs - startedAtMs);
    sseEventsPerStream.add(eventCount);
  }

  check(response, {
    'sse connected': (r) => r && (r.status === 200 || r.status === 0),
    'received [DONE]': () => sawDone,
    'received at least 1 event': () => eventCount > 0,
  });
}
