# Monitoring module — CloudWatch billing alarms for spend alerts.
#
# NOTE: AWS billing metrics live ONLY in us-east-1, regardless of where the app
# runs. This module must be instantiated with a us-east-1 provider (the env wires
# a provider alias). Alarms fire at 50/75/90% of the monthly budget → SNS.

variable "name_prefix" { type = string }
variable "monthly_budget_usd" {
  type    = number
  default = 300 # target: < $300/mo @ 10k MAU.
}
variable "alert_emails" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}
# Log retention policy. Default 90d = "access" class
# (see docs/hardening/log-retention-policy.md); override per call-site to 365
# for "security" class, 7 for "debug" class.
variable "log_retention_days" {
  type        = number
  default     = 90
  description = "CloudWatch log group retention (days). 90=access, 365=security, 7=debug."
}

resource "aws_sns_topic" "billing" {
  name = "${var.name_prefix}-billing-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  for_each  = toset(var.alert_emails)
  topic_arn = aws_sns_topic.billing.arn
  protocol  = "email"
  endpoint  = each.value
}

locals {
  thresholds = { "50" = 0.5, "75" = 0.75, "90" = 0.9 }
}

resource "aws_cloudwatch_metric_alarm" "billing" {
  for_each            = local.thresholds
  alarm_name          = "${var.name_prefix}-billing-${each.key}pct"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600 # 6h — billing metrics update slowly
  statistic           = "Maximum"
  threshold           = var.monthly_budget_usd * each.value
  alarm_description   = "Estimated monthly charges exceeded ${each.key}% of $${var.monthly_budget_usd} budget"
  dimensions          = { Currency = "USD" }
  alarm_actions       = [aws_sns_topic.billing.arn]
  tags                = var.tags
}

output "sns_topic_arn" { value = aws_sns_topic.billing.arn }
