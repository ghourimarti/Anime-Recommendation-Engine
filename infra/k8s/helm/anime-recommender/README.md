# anime-recommender Helm chart

Deploys the whole app: **api** (Argo Rollouts canary), **web** (Deployment+HPA),
**worker** (Deployment + KEDA ScaledObject per queue), **migrate** (pre-upgrade
hook), plus IRSA ServiceAccounts, ESO `ExternalSecret`, Ingress, ResourceQuota +
NetworkPolicy.

## In-cluster prerequisites
Argo Rollouts · KEDA · External Secrets Operator · ArgoCD · an ingress controller
(AWS ALB or nginx). The chart emits their CRDs assuming the controllers exist.

## Lint + render + validate (no cluster)
```bash
cd infra/k8s/helm/anime-recommender
helm lint . -f values-dev.yaml
helm template anime-recommender . -f values-dev.yaml | \
  kubeconform -ignore-missing-schemas -strict -summary
```
`-ignore-missing-schemas` skips the CRDs (Rollout/ScaledObject/ExternalSecret)
whose schemas aren't in the stock k8s set.

## Per-env values
| knob | dev | staging | prod |
|---|---|---|---|
| api replicas | 1 | 2 | 3 |
| web HPA | off | 2–8 | 3–20 |
| feedback worker min | 1 | 1 | 2 |
| OTel | off | on | on |
| namespace | anime-dev | anime-staging | anime-prod |

Before deploy, paste the Terraform outputs into each env's values:
`serviceAccount.{api,worker}.roleArn`, `image.registry`, `sqsQueueUrlBase`.

## GitOps
`infra/k8s/argocd/applicationset.yaml` generates one ArgoCD Application per env.
The migrate Job runs as a PreSync hook; the api canary + AnalysisTemplate gate
the rollout and auto-roll-back on a success-rate dip.

## Worker manifests
`infra/k8s/workers/*.yaml` are the standalone reference; **this chart's
`templates/worker.yaml` is the deploy source of truth.**
