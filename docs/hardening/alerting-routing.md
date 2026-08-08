# Alerting Routing

Wires the existing CloudWatch billing alarms (the cost-control layer) to two
destinations: **Slack** (incoming webhook → Lambda formatter → SNS) and
**email** (direct SNS subscription).

**Out of scope for v1:** PagerDuty integration — deferred until the live
environment exists. Documented at the bottom.

---

## 1. The wiring

```
CloudWatch billing alarm (50/75/90% of monthly budget)
        │
        ▼
SNS topic: aws_sns_topic.billing                  ← main.tf (existing)
        │
        ├─► aws_sns_topic_subscription "email"    ← main.tf (existing)
        │      protocol = "email"
        │      endpoint = each(var.alert_emails)
        │
        └─► aws_sns_topic_subscription "slack"    ← slack.tf
               protocol = "lambda"
               endpoint = aws_lambda_function.slack_alerts.arn
                            │
                            ▼
                Lambda (lambda_slack.js)
                  formats CloudWatch alarm payload into Slack JSON
                  POST → SLACK_WEBHOOK_URL (env var)
                            │
                            ▼
                   Slack channel
```

Both subscriptions are independent — disabling one (e.g. clearing
`slack_webhook_url`) doesn't affect the other.

---

## 2. The webhook-URL flow (the load-bearing part)

The Slack webhook URL must never touch git. Three hops:

```
GitHub repo Variable     ──┐
  (Settings → Secrets and  │
   Variables → Variables   │
   → SLACK_WEBHOOK_URL)    │
                           ▼
GitHub Actions workflow exports it
  -var "slack_webhook_url=${{ vars.SLACK_WEBHOOK_URL }}"
                           │
                           ▼
Terraform apply consumes the var
  variable "slack_webhook_url" {
    type      = string
    sensitive = true     ← protects it from being logged
    default   = ""       ← empty default disables the whole Slack stack
  }
                           │
                           ▼
Lambda environment variable
  environment.variables.SLACK_WEBHOOK_URL = var.slack_webhook_url
                           │
                           ▼
Lambda code reads process.env.SLACK_WEBHOOK_URL at invocation
  → POSTs to the webhook
```

No file on disk in this repo contains the webhook URL. Rotating the
webhook means: regenerate in Slack → update the GitHub Variable → next
`terraform apply` propagates the new value.

If `var.slack_webhook_url` is empty (the default), the whole Slack stack
is conditional-skipped via `local.slack_enabled = var.slack_webhook_url != ""`.
The module remains valid when Slack isn't wired.

---

## 3. Mint the Slack webhook (one-time)

1. Slack admin: *Apps → Incoming Webhooks → Add new webhook to workspace*.
2. Select the destination channel (recommended: `#anime-recommender-alerts`).
3. Copy the URL (`https://hooks.slack.com/services/T.../B.../X...`).
4. GitHub repo: *Settings → Secrets and variables → Actions → Variables → New repository variable*:
   - Name: `SLACK_WEBHOOK_URL`
   - Value: the URL from step 3
5. (Optional) In the same place, create `OPS_EMAIL` if you want the
   billing alarms going to a specific ops mailing list rather than your
   personal address.

---

## 4. Apply

```bash
cd infra/terraform/envs/dev
terraform init
terraform plan \
    -var "slack_webhook_url=$SLACK_WEBHOOK_URL" \
    -var 'alert_emails=["ops@example.com"]'

# If the plan looks right:
terraform apply \
    -var "slack_webhook_url=$SLACK_WEBHOOK_URL" \
    -var 'alert_emails=["ops@example.com"]'
```

`SLACK_WEBHOOK_URL` here is exported from the local shell (your one-off
apply) OR set as a `TF_VAR_slack_webhook_url` env var.

---

## 5. Test the wiring (dry-run)

Use the same `set-alarm-state` procedure from
`docs/hardening/cost-alert-verification.md` §3b:

```bash
aws cloudwatch set-alarm-state \
    --alarm-name anime-billing-50pct \
    --state-value ALARM \
    --state-reason "alerting verification — Slack wiring test"
```

**Verify within 2 minutes:**

- **Email**: ops mailing list receives an SNS notification.
- **Slack**: target channel gets a colored attachment (red because state=ALARM)
  with `AlarmName`, `Region`, `Account`, `Reason`, `Description`.
- **CloudWatch log group** `/aws/lambda/anime-billing-slack-alerts` shows
  a Lambda invocation with status code 200.

Reset the alarm with `--state-value OK` to send the "recovered" message
(should appear in green).

If Slack doesn't fire but email does → check the Lambda CloudWatch logs;
likely either `SLACK_WEBHOOK_URL` empty/wrong or the webhook rate-limited.

If email doesn't fire but Slack does → the SNS email subscription wasn't
confirmed (each email subscriber must click the AWS confirmation link
when first subscribed).

---

## 6. Slack message shape

Colored attachment, one per alarm:

| Field | Source |
|---|---|
| Color | `#d62728` (ALARM), `#2ca02c` (OK), `#7f7f7f` (INSUFFICIENT_DATA) |
| Title | `*<AlarmName>* — <NewStateValue>` |
| Region | `event.Records[0].Sns.Message.Region` |
| Account | `AWSAccountId` |
| Reason | `NewStateReason` (truncated 500 chars) |
| Description | `AlarmDescription` (truncated 300 chars) |
| Footer | `anime-recommender · CloudWatch → Lambda → Slack` |
| Timestamp | `now()` |

Adjust at `infra/terraform/modules/monitoring/lambda_slack.js` if the
shape needs to evolve (e.g. add a Grafana link / runbook URL for each
alarm type).

---

## 7. PagerDuty — deferred

PagerDuty subscription needs:
- A real production environment (so the on-call schedule has somewhere to
  point — the prod stage).
- A paid PagerDuty service account.
- A "Custom Event Transformer" integration OR an EventBridge → PagerDuty
  CloudWatch integration.

The future plan:

```
SNS billing topic
        │
        ▼
  EventBridge rule (cross-region, since billing is us-east-1)
        │
        ▼
  PagerDuty CloudWatch integration
        │
        ▼
  On-call schedule → SMS / phone call / push
```

For now: Slack + email cover all v1 + early production needs. PagerDuty
will be added when the prod environment exists and on-call requires
non-Slack escalation.

---

## 8. Design rationale

Implements the operational discipline behind:
- **Cost controls** — the alarms need destinations, not just thresholds.
- **AWS-native pattern** — SNS + Lambda.
- **Secrets management** — the webhook lives in a TF var, not in the repo.

When the routing changes (e.g. add PagerDuty), update this doc + the
Terraform together in a single PR.
