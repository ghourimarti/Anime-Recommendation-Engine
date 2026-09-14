# anime-recommender Helm chart

Deploys the whole app: **api** (Argo Rollouts canary, or a plain Deployment),
**web** (Deployment+HPA), **worker** (Deployment + KEDA ScaledObject per queue),
**migrate** (pre-upgrade hook), plus ServiceAccounts, ESO `ExternalSecret`,
Ingress, ResourceQuota + NetworkPolicy — each optional where a cluster can't
provide it.

## Values layering: base → vendor → env
```bash
helm template anime . -f values.yaml -f values-<vendor>.yaml [-f values-<env>.yaml]
```
| layer | answers | owns |
|---|---|---|
| `values.yaml` | what the app needs anywhere | vendor-neutral defaults: ghcr.io registry, tag → `appVersion` |
| `values-local` · `values-doks` · `values-aws` | what the cluster provides | registry, secret backend, ingress class, KEDA auth, NetworkPolicy source |
| `values-dev` · `values-staging` · `values-prod` | how big, which names | replicas, HPA, hosts, prefixes, IRSA ARNs |

Always layer a vendor file. The base alone deploys nowhere — KEDA is on and
`sqsQueueUrlBase` is empty, so it fails at render time, deliberately, rather
than guessing a cloud.

## Toggles by vendor
| | local (kind) | doks | aws |
|---|---|---|---|
| `rollout.enabled` | off → Deployment | on | on |
| `keda.enabled` | off | off — Phase 8 decision (SQS without IRSA) | on, IRSA |
| `externalSecrets.enabled` | off | off — P8.6 decision | on, AWS Secrets Manager |
| ingress | disabled (port-forward) | nginx | alb |
| `networkPolicy` | off — kindnet doesn't enforce | ingress-nginx namespace | VPC CIDR (ALB IP mode) |
| `image.registry` | none (`kind load`) | ghcr.io | ECR — see Phase 9 blockers in `values-aws.yaml` |

In-cluster prerequisites follow from the toggles: Argo Rollouts where `rollout`
is on, KEDA where `keda` is on, ESO where `externalSecrets` is on, and the
controller named by `ingress.className`.

The api Rollout and its Deployment fallback share one pod template
(`anime.api.podTemplate`), so the toggle changes the delivery strategy and
nothing else.

## Image tags
Per-component `digest` → per-component `tag` → `image.tag` → `appVersion` in
`Chart.yaml`. An empty result fails the render; `:latest` is never the default.

## Verify (no cluster)
```bash
make render-verify      # needs helm, kubeconform, curl
```
Renders all 12 vendor × env combinations and validates them with
`kubeconform -strict` against pinned Kubernetes v1.31 **and CRD** schemas. Not
`-ignore-missing-schemas`: that reports success by skipping the Rollout,
ScaledObjects and ExternalSecret — the resources most likely to be wrong. It also
checks local renders emit no CRD kind can't run, and runs negative controls
proving each check can fail.

## Per-env values
| knob | dev | staging | prod |
|---|---|---|---|
| api replicas | 1 | 2 | 3 |
| web HPA | off | 2–8 | 3–20 |
| feedback worker min | 1 | 1 | 2 |
| OTel | off | on | on |
| namespace | anime-dev | anime-staging | anime-prod |

On AWS, paste the Terraform outputs before deploy: `serviceAccount.{api,worker}.roleArn`
into each env file; `image.registry`, `sqsQueueUrlBase` and the VPC CIDR
(`networkPolicy.ingressFrom.cidrs`) into `values-aws.yaml`.

## GitOps
`infra/k8s/argocd/applicationset.yaml` generates one ArgoCD Application per env
on EKS, layering `values-aws.yaml` then `values-<env>.yaml` (ArgoCD loads
`values.yaml` implicitly). The migrate Job runs as a PreSync hook; the api
canary + AnalysisTemplate gate the rollout and auto-roll-back on a success-rate
or p95-latency regression.

## Worker manifests
`infra/k8s/workers/*.yaml` are the standalone reference; **this chart's
`templates/worker.yaml` is the deploy source of truth.**
