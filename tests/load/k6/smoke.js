// Smoke test — 1 RPS for 60s. Proves the harness is correctly wired before
// a real scenario burns five minutes of OpenAI spend on a broken setup.
//
// What this catches in 60s:
//   - Missing K6_AUTH_TOKEN (every /v1/recommend returns 401)
//   - Wrong BASE_URL (connection refused / DNS)
//   - Expired JWT (401 with specific Clerk error body)
//   - API not up (connection refused on /health)
//   - DB / Redis down (503 from /ready)
//
// Run:
//   k6 run -e BASE_URL=http://localhost:1005 -e K6_AUTH_TOKEN=$TOKEN tests/load/k6/smoke.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { authHeaders, hasToken } from './lib/auth.js';
import { pickQuery } from './lib/queries.js';
import { recordServerWorkMs } from './lib/metrics.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1005';

export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 4,
      maxVUs: 8,
    },
  },
  thresholds: {
    // Generous: smoke proves wiring, not performance.
    http_req_failed: ['rate<0.05'],            // <5% errors
    http_req_duration: ['p(95)<15000'],        // <15s p95 (cold caches)
    'http_req_duration{name:health}': ['p(95)<200'],
    'http_req_duration{name:ready}': ['p(95)<1000'],
  },
};

export function setup() {
  if (!hasToken()) {
    throw new Error(
      'K6_AUTH_TOKEN is not set. Export a Clerk dev-tenant JWT — see ' +
        'tests/load/README.md §2 for the mint procedure.',
    );
  }
  // Pre-flight: /health must respond before we start sending real traffic.
  const r = http.get(`${BASE_URL}/health`, { tags: { name: 'health' } });
  if (r.status !== 200) {
    throw new Error(
      `/health returned ${r.status} — is the API up? Try: make dev-api`,
    );
  }
  return { baseUrl: BASE_URL };
}

export default function (data) {
  // 50% /health (cheap warmup), 50% /v1/recommend (real path).
  // eslint-disable-next-line no-undef
  if (__ITER % 2 === 0) {
    const r = http.get(`${data.baseUrl}/health`, { tags: { name: 'health' } });
    check(r, { 'health 200': (res) => res.status === 200 });
  } else {
    const body = JSON.stringify({ query: pickQuery() });
    const params = {
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      tags: { name: 'recommend' },
      timeout: '30s',
    };
    const r = http.post(`${data.baseUrl}/v1/recommend`, body, params);
    check(r, {
      'recommend 200': (res) => res.status === 200,
      'recommend has recommendations': (res) => {
        try {
          const j = res.json();
          return Array.isArray(j.recommendations) && j.recommendations.length > 0;
        } catch (_) {
          return false;
        }
      },
    });
    recordServerWorkMs(r);
  }
  sleep(0.1); // tiny stagger to avoid lockstep VU iteration
}
