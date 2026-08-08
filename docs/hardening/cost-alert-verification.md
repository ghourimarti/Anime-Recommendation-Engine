# Cost-Alert Verification

The Terraform `monitoring` module (`infra/terraform/modules/monitoring`)
provisions CloudWatch billing alarms at 50% / 75% / 90% / 200% of the
configured monthly budget, plus the SNS → Lambda → feature-flag wiring that
flips `LLM_ENABLED=false` at 200% (the kill switch).

This doc is the **dry-run procedure** to verify those trip wires actually
fire end-to-end. Run it **once after each new environment is provisioned**
(dev first, then staging) and **whenever the alarm thresholds
change**.

Reason for verifying: a tested alarm that fires is observability. An
untested alarm is wishful thinking.

---

## 1. Pre-requisites

- Terraform has been applied for the environment under test.
- AWS CLI configured for the same account/region as the deployment
  (`aws sts get-caller-identity` returns the deploy role).
- SNS topic subscription confirmed (email / Slack webhook). Without this,
  alarms fire but you don't see anything.
- `kubectl` configured for the EKS cluster (`kubectl get nodes` works).

---

## 2. The alarms under test

| Alarm name | Threshold | Action | Source |
|---|---|---|---|
| `anime-spend-50` | 50% of monthly budget | SNS notification (info) | TF `monitoring.budget_50_pct` |
| `anime-spend-75` | 75% of monthly budget | SNS notification (warn) | TF `monitoring.budget_75_pct` |
| `anime-spend-90` | 90% of monthly budget | SNS notification (warn) + on-call ping | TF `monitoring.budget_90_pct` |
| `anime-spend-200-kill` | 200% of monthly budget | SNS → Lambda → flip `LLM_ENABLED=false` | TF `monitoring.budget_200_pct_kill_switch` |

Confirm the alarm names match in the AWS console (CloudWatch → Alarms). If
any name has drifted in Terraform, update the table.

---

## 3. Verification procedure

### 3a. Verify each alarm exists and is in OK state

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix anime-spend- \
  --state-value OK \
  --query 'MetricAlarms[].[AlarmName,StateValue,MetricName,Threshold,Statistic]' \
  --output table
```

**Expect:** 4 alarms, all `OK`. If any are `INSUFFICIENT_DATA`, that's
expected on day 0 (billing metrics lag ~6h); re-check after 12h. If any
are `ALARM`, that's a real signal — go to the cost-spike runbook.

### 3b. Dry-run trip the 50% alarm

Don't actually spend money. Use `set-alarm-state` to simulate.

```bash
aws cloudwatch set-alarm-state \
  --alarm-name anime-spend-50 \
  --state-value ALARM \
  --state-reason "cost-alert verification — dry-run trip"
```

**Verify within 2 minutes:**

- Email subscription receives the notification.
- Slack webhook receives the notification (channel: `#anime-recommender-alerts`).
- CloudWatch console shows the alarm in `ALARM` state with the dry-run reason.

Then reset:

```bash
aws cloudwatch set-alarm-state \
  --alarm-name anime-spend-50 \
  --state-value OK \
  --state-reason "cost-alert verification complete"
```

### 3c. Dry-run trip the 200% kill switch

THIS IS THE LOAD-BEARING TEST. The kill switch is the last line of defense
when distributed cost regression escapes the earlier alarms.

```bash
aws cloudwatch set-alarm-state \
  --alarm-name anime-spend-200-kill \
  --state-value ALARM \
  --state-reason "cost-alert verification — kill-switch end-to-end test"
```

**Verify within 5 minutes:**

```bash
# Lambda execution log shows the kill switch ran
aws logs tail /aws/lambda/anime-cost-kill-switch --since 5m

# The Deployment env was patched
kubectl get deploy/anime-api -n anime-dev -o jsonpath='{.spec.template.spec.containers[0].env}' \
  | jq '.[] | select(.name == "LLM_ENABLED")'
# Expect: {"name": "LLM_ENABLED", "value": "false"}

# A request to /v1/recommend now returns the friendly degradation response
curl -X POST https://api.anime-dev.example.com/v1/recommend \
  -H "Authorization: Bearer $TEST_JWT" \
  -H "Content-Type: application/json" \
  -d '{"query":"anything"}'
# Expect: 503 with body {"detail": "Service temporarily unavailable — please try again shortly."}
```

**Then RESET** (else the env stays disabled):

```bash
# Re-enable the LLM
kubectl set env deploy/anime-api -n anime-dev LLM_ENABLED=true

# Reset the alarm
aws cloudwatch set-alarm-state \
  --alarm-name anime-spend-200-kill \
  --state-value OK \
  --state-reason "cost-alert verification complete"

# Confirm the env is back
kubectl get deploy/anime-api -n anime-dev -o jsonpath='{.spec.template.spec.containers[0].env}' \
  | jq '.[] | select(.name == "LLM_ENABLED")'
# Expect: {"name": "LLM_ENABLED", "value": "true"}
```

---

## 4. What to check if any step fails

| Failure | Probable cause | Where to fix |
|---|---|---|
| Email not received | SNS subscription unconfirmed | AWS Console → SNS → Topics → confirm subscription |
| Slack not received | Webhook URL invalid or expired | Regenerate webhook in Slack; update GitHub Secret `SLACK_WEBHOOK_URL`; re-deploy Lambda |
| Lambda log shows "AccessDenied: PatchDeployment" | Lambda's IAM role missing K8s permissions | TF: `monitoring.kill_switch_lambda_role` policy needs `eks:DescribeCluster` + an aws-auth ClusterRoleBinding |
| Env var didn't flip | Lambda silently failed | Lambda CloudWatch logs → check the exception; rare = race with a deploy |
| `/v1/recommend` still 200s after env flip | Pods didn't restart | `kubectl rollout restart deploy/anime-api` |

---

## 5. Documentation discipline

Run this verification AT LEAST:

- On every new environment provisioning (dev / staging / prod).
- After any change to `infra/terraform/modules/monitoring`.
- Quarterly, as part of the runbook freshness review.

Record the date + environment in this section so the next person can see
the last successful run.

| Date | Environment | Operator | Result |
|---|---|---|---|
| _(not yet run — pending the dev apply)_ | — | — | — |

---

## 6. Design rationale

This procedure implements the operational discipline behind:

- **Cost controls** — layered, with a documented kill switch at 200%.
- **AWS-native realization** — CloudWatch alarms + SNS + Lambda.

When the alarms behave differently from what's described here, update the
notes and this doc together.
