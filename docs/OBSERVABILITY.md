# Observability

Three questions, three dashboards: *is the product working*, *which model answered
and why*, *is the machine underneath healthy*. Everything below is provisioned —
`make up-obs` (or any `make up*`) brings it up with the dashboards already loaded.

| Dashboard | UID | Answers |
|---|---|---|
| Anime Recommender - overview | `api-overview` | Is the product working? What is it serving, where does the time go, what does it cost, who answered |
| LLM and venue routing | `anime-llm-venue` | Why a request went to the GPU or to a hosted provider, and whether the engine is healthy |
| Infrastructure | `anime-infra` | Postgres, Redis, containers, the Docker VM, storage, trace store, telemetry pipeline |

Grafana: <http://localhost:1019> · Prometheus targets: <http://localhost:1018/targets> ·
`make service_ls` prints every endpoint with credentials.

## How the metrics get there

Two paths, deliberately:

```
app  ──OTLP push──>  otel-collector :8889  ──┐
                                             ├──>  Prometheus  ──>  Grafana
everything else  ──scraped directly──────────┘
```

The application never exposes `/metrics` itself. It pushes OpenTelemetry to the
collector, which re-exposes the series for Prometheus — the same shape as a
managed OTLP backend, so moving to one is a config change, not a code change.
Infrastructure is scraped directly from the component that owns it.

### Scrape targets

| Job | Target | Notes |
|---|---|---|
| `app` | otel-collector:8889 | the `anime_*` series |
| `otel-collector` | otel-collector:8888 | the collector's own health: queue depth, refused/dropped points |
| `venue-engine` | anime-venue:8000 | vLLM **or** SGLang — `anime-venue` is a network alias the venue scripts attach |
| `postgres-app` / `postgres-langfuse` | postgres-exporter:9187 | two exporters, two databases |
| `redis-app` / `redis-langfuse` | redis-exporter:9121 | cache and Langfuse queues |
| `minio` | minio:9000 | `MINIO_PROMETHEUS_AUTH_TYPE=public` locally |
| `clickhouse` | clickhouse:9363 | enabled by `infra/clickhouse-config.d/prometheus.xml` |
| `cadvisor` / `node` | cadvisor:8080, node-exporter:9100 | containers and the Docker VM |
| `grafana` / `prometheus` | self | the observability stack itself |

**A target that is DOWN is information, not a defect.** `venue-engine` is down
whenever the stack runs in API-LLM mode (`make up`), and the data-tier exporters
are down when only the obs tier is running (`make up-obs`). They stay in the
config rather than being deleted so their absence is visible.

## Application metrics

| Metric | Attributes | Why it exists |
|---|---|---|
| `anime.http.requests` / `.duration` | route, method, status_code, status_class | Canary analysis gates on these names |
| `anime.llm.calls` / `.tokens` / `.cost.usd` | model, direction, outcome | Per-model spend; the venue meters at $0 |
| `anime.llm.unpriced.calls` | model | Billed by the provider, metered at $0 — a billing hole |
| `anime.llm.refusals` | — | Honest declines. Healthy, but a spike means abuse or a retrieval regression |
| `anime.llm.venue.decisions` | decision | hosted / venue_served / venue_fallback_error / venue_fallback_empty |
| `anime.retrieval.confidence` | — | Top-1 rerank relevance as a probability. Threshold 1.0 in logit space = **0.731** here |
| `anime.retrieval.stage.duration` | stage, outcome | embed / dense / sparse / rerank / mmr, incl. failures with the time they burned |
| `anime.cache.lookups` | result, path | Response-cache hit rate — most of the cost story |
| `anime.circuit.transitions` | breaker, state | Only on an actual state change, so a flap is visible |
| `anime.quota.rejections` | scope | 429s are in the HTTP metrics; this says *why* |
| `anime.worker.jobs` / `.poison.messages` | queue, outcome | Queue consumer health |

Cardinality is bounded by construction: route templates, model names and enum-ish
outcomes only. Never add a user id, query string or trace id as an attribute.

## The one thing worth understanding: routing is fail-safe

`should_use_venue(confidence)` sends a request to the self-hosted GPU only when
retrieval was *measurably* confident. Confidence is the top-1 rerank score, and
the reranker runs under `RERANK_TIMEOUT` (2s). If it misses that budget there is
**no score**, and no score means the hosted chain.

That is correct behaviour, and it is also indistinguishable from "the GPU is
broken" unless you measure it. On 2026-09-16 every routing decision on this host
came out `hosted` while vLLM sat healthy and idle: reranking ~20 candidates
simply did not fit in 2s. Three panels make that legible now:

- **Confidence samples / sec** (LLM dashboard) — zero while traffic flows means no
  signal is being produced at all.
- **Rerank timeouts / sec** — the direct cause.
- **Confidence percentiles vs the 0.731 threshold** — if p99 sits below the line,
  the venue can never be selected no matter how healthy the engine is.

When that happens the fix is to make reranking fit its budget, or to re-derive the
threshold against real traffic — not to nudge the threshold until something routes.

## Known limitation on this host

Per-container CPU/memory is **not available** under Docker Desktop's containerd
image store: cAdvisor cannot identify containers (`failed to identify the
read-write layer ID`, because `/var/lib/docker/image` has no `layerdb`), and it is
not given the per-container cgroups either — it sees only `/`, `/docker` and
`/docker/buildkit`. The Infrastructure dashboard therefore shows container
resources in aggregate, with the VM total alongside.

To get a per-container split, turn off *Use containerd for pulling and storing
images* in Docker Desktop → Settings → General. The dashboard queries already
select on `id` and print whichever label exists, so they gain the per-container
breakdown with no edit.

## Adding a panel

Dashboards are provisioned from `infra/observability/grafana/dashboards/*.json`
and reload every 30s — edit the JSON, save, refresh the browser. Two rules the
existing panels follow:

1. **Every panel has a `description`.** A panel whose meaning lives only in the
   author's head is a panel that gets misread during an incident.
2. **Ratios use `or vector(0)`** on both sides. A counter with no series yet makes
   a bare division return *No data*, which reads like a broken panel rather than
   "this has not happened".

Validate before committing — this catches a typo'd metric name, which otherwise
just renders an empty graph:

```bash
curl -s -G http://localhost:1018/api/v1/query --data-urlencode 'query=<your expr>'
```
