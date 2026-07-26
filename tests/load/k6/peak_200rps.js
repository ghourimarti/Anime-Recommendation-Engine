// Peak 200 RPS for 90s — burst headroom validation.
//
// NFR: designed-for peak ≈ 200 RPS. Sustained is the gate; this is
// the burst test (90s, not 5m: peak = burst, not sustained). If the system
// can't hold 200 RPS for 90s, autoscaling never gets to engage in prod.
//
// Thresholds are relaxed vs sustained — we expect tail latency growth at peak.
// What we DON'T accept: error rate growing significantly.
//
// Run:
//   k6 run -e BASE_URL=http://localhost:1005 -e K6_AUTH_TOKEN=$TOKEN \
//          --summary-export=tests/load/reports/peak_200rps_$(date +%s).json \
//          tests/load/k6/peak_200rps.js

import http from 'k6/http';
import { check } from 'k6';
import { authHeaders } from './lib/auth.js';
import { pickQuery } from './lib/queries.js';
import { recordServerWorkMs } from './lib/metrics.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1005';

export const options = {
  scenarios: {
    peak: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '90s',
      preAllocatedVUs: 400,
      maxVUs: 800,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    // At peak we allow degradation but still cap error rate.
    http_req_failed: ['rate<0.02'],            // <2% errors (vs 1% sustained)
    http_req_duration: [
      'p(95)<15000',
      'p(99)<30000',
    ],
    anime_server_work_ms: ['p(95)<14000'],
  },
};

export default function () {
  const body = JSON.stringify({ query: pickQuery() });
  const params = {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    tags: { name: 'recommend' },
    timeout: '60s',
  };
  const r = http.post(`${BASE_URL}/v1/recommend`, body, params);
  check(r, {
    'status 200': (res) => res.status === 200,
  });
  recordServerWorkMs(r);
}
