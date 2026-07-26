// Sustained 50 RPS for 5 min — THE NFR-validating scenario.
//
// Thresholds map to the NFRs:
//   - http_req_failed < 1%               (uptime SLO)
//   - http_req_duration p50 < 3000       (full response p50 < 3s)
//   - http_req_duration p95 < 8000       (full response p95 < 8s)
//   - anime_server_work_ms p95 < 7500    (server-side ≤ network+serialization headroom)
//
// constant-arrival-rate executor (NOT ramping-vus): we measure what the server
// can produce at a target rate, not what our VUs can produce given latency.
// This is the only executor that legitimately tests an SLO.
//
// Run:
//   k6 run -e BASE_URL=http://localhost:1005 -e K6_AUTH_TOKEN=$TOKEN \
//          --summary-export=tests/load/reports/sustained_50rps_$(date +%s).json \
//          tests/load/k6/sustained_50rps.js

import http from 'k6/http';
import { check } from 'k6';
import { authHeaders } from './lib/auth.js';
import { pickQuery } from './lib/queries.js';
import { recordServerWorkMs } from './lib/metrics.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1005';

export const options = {
  scenarios: {
    sustained: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 100,
      maxVUs: 200,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: [
      'p(50)<3000',
      'p(95)<8000',
      'p(99)<15000',
    ],
    anime_server_work_ms: [
      'p(50)<2800',
      'p(95)<7500',
    ],
  },
};

export default function () {
  const body = JSON.stringify({ query: pickQuery() });
  const params = {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    tags: { name: 'recommend' },
    timeout: '30s',
  };
  const r = http.post(`${BASE_URL}/v1/recommend`, body, params);
  check(r, {
    'status 200': (res) => res.status === 200,
    'has recommendations': (res) => {
      try {
        return Array.isArray(res.json().recommendations);
      } catch (_) {
        return false;
      }
    },
  });
  recordServerWorkMs(r);
}
