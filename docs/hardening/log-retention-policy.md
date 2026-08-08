# Log Retention Policy

The policy that maps every log surface in the system to a class with an
explicit retention window. Class defaults below; per-resource overrides
allowed when the operational reason is documented in the same place as
the override.

**Implements:** GDPR Article 5(1)(e) ("storage limitation") — a config
policy applied uniformly, plus PII handling.

---

## 1. Classes

| Class | Retention | Rationale |
|---|---|---|
| **security** | 365 days | Audit, authentication failures, access-control violations, RTBF events. Required for forensic analysis + compliance evidence. Must survive a one-quarter incident-detection lag. |
| **access** | 90 days | App/HTTP access logs, alarm-trigger events, deploy/release logs. Long enough to investigate "what happened last quarter?", short enough that PII exposure window stays bounded. |
| **debug** | 7 days | Verbose application logs, OTel traces sampled at high rate, vendor-tool noise. The minimum useful window for "diagnose yesterday's incident"; longer adds cost without proportional value. |

Anything not classified gets the **access** default. Don't store something
unclassified; pick a class.

---

## 2. Surface → Class mapping

| Log surface | Class | Notes |
|---|---|---|
| `/aws/lambda/anime-billing-slack-alerts` | access | Slack-routing Lambda — alerting hop; useful to debug delivery failures for ~90d |
| `/aws/rds/anime-prod` (Postgres engine logs) | access | Slow queries, errors; longer if auditing required |
| `/aws/eks/anime-{dev,staging,prod}/cluster` (control plane) | security | Authentication + authorization events; 1y for SOC 2-style evidence |
| Application logs (api/web/worker → CloudWatch via FluentBit) | access | App-level errors + access patterns; PII redacted at the structlog layer |
| OTel traces (sampled to Grafana Tempo / Langfuse) | debug | High-volume, value decays fast; rely on RAGAS regression for longer-term quality signal |
| Audit table `account_deletions` | security (in-DB, not CloudWatch) | Lives in Postgres; survives log expiry by design (single row per deletion) |
| Audit table `usage_daily` | access (in-DB) | Cost meter; pruned only on user RTBF |

---

## 3. Terraform realization

Each module that creates a `aws_cloudwatch_log_group` consumes
`var.log_retention_days`. The monitoring module exposes the variable with
the **access** default (90 days). Modules that handle security-class
surfaces (e.g. EKS audit logs) pass a different value at the call site.

```hcl
# monitoring module (this file mints the variable):
variable "log_retention_days" {
  type    = number
  default = 90   # access class
}

# slack.tf log group uses it:
resource "aws_cloudwatch_log_group" "slack_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-slack-alerts"
  retention_in_days = var.log_retention_days
}

# At an env composition, per-surface overrides look like:
module "monitoring" {
  source             = "../../modules/monitoring"
  name_prefix        = "anime-prod"
  log_retention_days = 90      # access class — the slack lambda
}

module "eks_audit_logs" {
  source             = "../../modules/eks"
  name_prefix        = "anime-prod"
  log_retention_days = 365     # security class — control-plane events
}
```

---

## 4. Local + dev exemptions

Local dev (docker compose) and Langfuse self-hosted (in-cluster) don't go
through CloudWatch — their retention is governed differently:

| Surface | Where retention lives | Default |
|---|---|---|
| docker compose logs (local) | `docker compose logs --since N` window | 24h effective (container lifetime) |
| Langfuse traces (self-hosted) | Langfuse config: `LANGFUSE_TRACE_RETENTION_DAYS` | 30 days (set in helm values for staging/prod) |
| Local Postgres logs | Postgres `log_min_duration_statement` + local rotation | 7 days; not PII-sensitive in dev |

---

## 5. Compliance checklist

- [x] Every CloudWatch log group consumed by Terraform has explicit `retention_in_days` (no "never expire" defaults left to AWS).
- [x] Application-level logs are PII-redacted BEFORE they reach the log surface.
- [x] RTBF events log to `account_deletions` AND to a security-class CloudWatch group so the deletion fact survives the access-class window.
- [ ] Quarterly retention-cost review: confirm the policy hasn't drifted into "everything 365 days" by inertia. Owner: Zaini.

---

## 6. Drift detection

The policy is text. Drift between policy and reality is the failure
mode. Quarterly:

```bash
aws logs describe-log-groups --query 'logGroups[].[logGroupName,retentionInDays]' \
    --output table
```

Any row where `retentionInDays = None` (i.e. AWS default "never expire") is
non-compliant. Update the relevant Terraform module + apply.

---

## 7. Design rationale

- **Secrets / config management**: retention is a config policy
  applied uniformly via TF variables, not per-resource one-offs.
- **Security posture / PII handling**: retention is the *time* axis
  of PII exposure; redaction is the *content* axis. Both required.
- **AWS-native**: CloudWatch log groups are the realization layer.

---

## 8. History

| Date | Change | By |
|---|---|---|
| 2026-06-12 | Initial policy: security/access/debug classes; access=90d default; monitoring module exposes variable | Zaini |
