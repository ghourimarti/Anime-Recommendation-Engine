// Custom k6 metrics + helpers shared across scenarios.
//
// Why a central lib: cross-scenario dashboards (Grafana, k6 Cloud) compare
// metrics by exact name. If each scenario file defines its own Trend with
// slightly different naming ("ttft" vs "llm_ttft" vs "time_to_first"),
// dashboards can't aggregate across scenarios. One source of truth.

import { Trend, Counter, Rate } from 'k6/metrics';

// X-Server-Ms — server-side recommend pipeline time emitted by
// anime_api.middleware.ServerTimingMiddleware.
// This is the load-test signal for "how fast is the server's work, isolated
// from network and serialization." Compare against http_req_duration to
// estimate network overhead.
export const serverWorkMs = new Trend('anime_server_work_ms', true);

// SSE (xk6-sse) — time to first event from /v1/recommend/stream. THE TTFT
// metric for the streaming UX. NFR target: p50 < 800 ms, p95 < 2.5s.
export const sseTtftMs = new Trend('anime_sse_ttft_ms', true);

// SSE total — full stream duration (connect → [DONE] event).
export const sseTotalMs = new Trend('anime_sse_total_ms', true);

// SSE token throughput — events received per stream.
export const sseEventsPerStream = new Trend('anime_sse_events_per_stream');

// SSE connect failures — distinct from request failures because xk6-sse
// reports differently than http_req_failed.
export const sseConnectErrors = new Counter('anime_sse_connect_errors');

// Cache hit rate — derived from a custom response header (X-Cache: hit|miss)
// the API can emit. Optional; defaults to no-op if header absent.
export const cacheHitRate = new Rate('anime_cache_hit_rate');

// Helper — parse X-Server-Ms from a response and push to the Trend.
// Returns the parsed value (or null if absent), so callers can use it in
// custom k6 checks.
export function recordServerWorkMs(response) {
  const raw = response.headers['X-Server-Ms'];
  if (raw === undefined || raw === '') return null;
  const ms = parseFloat(raw);
  if (Number.isNaN(ms)) return null;
  serverWorkMs.add(ms);
  return ms;
}

// Helper — record cache-hit rate from X-Cache header (forward-compat: the API
// doesn't currently emit it; this is a no-op when absent and ready when
// observability is wired further).
export function recordCacheHit(response) {
  const raw = response.headers['X-Cache'];
  if (raw === undefined || raw === '') return;
  cacheHitRate.add(raw.toLowerCase() === 'hit' ? 1 : 0);
}
