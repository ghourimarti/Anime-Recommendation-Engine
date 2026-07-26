# Slack subscription for billing alarms.
#
# Subscribes a tiny Lambda formatter to the existing aws_sns_topic.billing
# topic from main.tf. The Lambda turns SNS payloads into colored Slack
# messages and posts to SLACK_WEBHOOK_URL.
#
# WHY a Lambda (not direct SNS HTTPS subscription): Slack incoming webhooks
# reject raw CloudWatch alarm payloads (they expect Slack's own JSON shape).
# The Lambda formats and forwards; 30 lines of Node.js, zero deps.
#
# Slack webhook URL is supplied at apply time:
#   TF_VAR_slack_webhook_url='https://hooks.slack.com/...' terraform apply
#   OR `terraform apply -var slack_webhook_url=...`
# Never store the webhook URL in a tracked .tfvars file. See
# docs/hardening/alerting-routing.md §2 for the GitHub-Variable flow.

variable "slack_webhook_url" {
  description = "Slack incoming-webhook URL for billing alerts. Leave empty to disable."
  type        = string
  default     = ""
  sensitive   = true
}

locals {
  slack_enabled = var.slack_webhook_url != ""
}

# ─── Lambda code package ─────────────────────────────────────────────────
data "archive_file" "slack_lambda" {
  count       = local.slack_enabled ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/lambda_slack.js"
  output_path = "${path.module}/lambda_slack.zip"
}

# ─── IAM role: basic execution + logs ────────────────────────────────────
data "aws_iam_policy_document" "slack_lambda_assume" {
  count = local.slack_enabled ? 1 : 0
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "slack_lambda" {
  count              = local.slack_enabled ? 1 : 0
  name               = "${var.name_prefix}-slack-alerts-role"
  assume_role_policy = data.aws_iam_policy_document.slack_lambda_assume[0].json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "slack_lambda_logs" {
  count      = local.slack_enabled ? 1 : 0
  role       = aws_iam_role.slack_lambda[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ─── Log group with explicit retention ───────────────────────────────────
# Reads from var.log_retention_days so the workspace-wide policy
# (docs/hardening/log-retention-policy.md) governs the value.
resource "aws_cloudwatch_log_group" "slack_lambda" {
  count             = local.slack_enabled ? 1 : 0
  name              = "/aws/lambda/${var.name_prefix}-slack-alerts"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ─── Lambda function ─────────────────────────────────────────────────────
resource "aws_lambda_function" "slack_alerts" {
  count            = local.slack_enabled ? 1 : 0
  function_name    = "${var.name_prefix}-slack-alerts"
  filename         = data.archive_file.slack_lambda[0].output_path
  source_code_hash = data.archive_file.slack_lambda[0].output_base64sha256
  handler          = "lambda_slack.handler"
  runtime          = "nodejs20.x"
  role             = aws_iam_role.slack_lambda[0].arn
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      SLACK_WEBHOOK_URL = var.slack_webhook_url
    }
  }

  # Ensure the log group exists before the function (so we control retention).
  depends_on = [aws_cloudwatch_log_group.slack_lambda]
  tags       = var.tags
}

# ─── SNS subscription: SNS → Lambda ──────────────────────────────────────
resource "aws_sns_topic_subscription" "slack" {
  count     = local.slack_enabled ? 1 : 0
  topic_arn = aws_sns_topic.billing.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.slack_alerts[0].arn
}

resource "aws_lambda_permission" "sns_invoke_slack" {
  count         = local.slack_enabled ? 1 : 0
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_alerts[0].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.billing.arn
}

output "slack_lambda_arn" {
  value       = local.slack_enabled ? aws_lambda_function.slack_alerts[0].arn : null
  description = "ARN of the Slack-formatter Lambda (null if slack_webhook_url is empty)"
  # Marked sensitive because Terraform's data-flow analysis propagates
  # sensitivity from the Lambda's environment block (which references the
  # sensitive `var.slack_webhook_url`). The ARN itself is not secret, but
  # Terraform errs on the conservative side.
  sensitive = true
}
