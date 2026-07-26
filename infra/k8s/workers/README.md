# Worker Deployments + KEDA autoscaling

Standalone worker manifests, validatable with `kubeconform` on their own. The
Helm chart (`infra/k8s/helm/anime-recommender`) is the deploy source of truth;
these mirror its worker templates for quick standalone inspection.

One **Deployment + ScaledObject per queue category** (feedback / ingestion /
housekeeping) so each scales independently:

- **KEDA** (`keda.sh/v1alpha1 ScaledObject`) scales the Deployment on SQS
  `ApproximateNumberOfMessages` — load follows queue depth, not CPU.
- `minReplicaCount: 1` avoids cold-start on the first message;
  `activationQueueLength` prevents flapping on a single message; scale-to-zero is
  a cost optimization once thresholds are tuned.
- A **DLQ** per queue (created by `anime_core.sqs.ensure_queues`, redrive
  `maxReceiveCount=5`) catches poison messages.

In-cluster prerequisites: KEDA installed, IRSA/role granting the worker
`sqs:ReceiveMessage|DeleteMessage|GetQueueAttributes`, and the same app config
(DATABASE_URL, REDIS_URL) the API uses.
