// Ramp 10 → 500 RPS over 10 min — diagnostic, NOT a gate.
//
// Purpose: find the architecture's knee (where p95 starts climbing
// non-linearly). Feeds the tuning playbook (tests/load/scenarios.md):
// when you see the knee at X RPS, the bottleneck order tells you which
// knob to turn next.
//
// IMPORTANT — no thresholds. Ramp tests are diagnostic. Setting thresholds
// would make this scenario "always fail at high RPS," teaching the team to
// ignore CI signals from it.
//
// Run:
//   k6 run -e BASE_URL=http://localhost:1005 -e K6_AUTH_TOKEN=$TOKEN \
//          --summary-export=tests/load/reports/ramp_$(date +%s).json \
//          tests/load/k6/ramp_to_knee.js

import http from 'k6/http';
import { authHeaders } from './lib/auth.js';
import { pickQuery } from './lib/queries.js';
import { recordServerWorkMs } from './lib/metrics.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1005';

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 1000,
      stages: [
        { duration: '2m', target: 50 },     // baseline target
        { duration: '2m', target: 100 },
        { duration: '2m', target: 200 },    // peak target
        { duration: '2m', target: 350 },
        { duration: '2m', target: 500 },    // beyond design
      ],
      gracefulStop: '30s',
    },
  },
  // No thresholds — diagnostic only. Inspect the summary + the recorded JSON
  // to find where p95 inflects vs RPS.
};

export default function () {
  const body = JSON.stringify({ query: pickQuery() });
  const params = {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    tags: { name: 'recommend' },
    timeout: '60s',
  };
  const r = http.post(`${BASE_URL}/v1/recommend`, body, params);
  recordServerWorkMs(r);
}
