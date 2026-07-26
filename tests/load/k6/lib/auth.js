// Auth header helper — single source of truth for "how a load-test VU authenticates".
//
// k6 scenarios import authHeaders() and spread it into params.headers. If
// K6_AUTH_TOKEN is unset, the helper returns no Authorization header and the
// request will 401 — that's intentional, the smoke test catches it before a
// sustained run wastes 5 min of OpenAI spend.
//
// Token source: a Clerk dev-tenant JWT minted
// once by the operator and exported as K6_AUTH_TOKEN. See tests/load/README.md
// §2 for the mint + rotation procedure. We use the real auth code path, not a
// test-only bypass — drift between test and prod auth is exactly the security
// regression we don't want to ship.

const TOKEN = __ENV.K6_AUTH_TOKEN || '';

export function authHeaders() {
  if (!TOKEN) {
    // No header → 401 → scenario reports a 100% failure rate, which is the
    // signal we want. Don't silently inject a fake token.
    return {};
  }
  return { Authorization: `Bearer ${TOKEN}` };
}

export function hasToken() {
  return Boolean(TOKEN);
}
