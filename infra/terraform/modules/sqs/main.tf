# SQS module — the prod queues + DLQs with redrive.
#
# Mirrors anime_core.sqs.ensure_queues (which bootstraps queues at runtime in
# dev/LocalStack). In prod the queues are IaC-managed so their ARNs are known to
# the IAM module (least-privilege scoping) at plan time.

variable "name_prefix" { type = string } # e.g. anime-prod
variable "categories" {
  type    = list(string)
  default = ["feedback", "ingestion", "housekeeping"]
}
variable "max_receive_count" {
  type    = number
  default = 5
}
variable "kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_sqs_queue" "dlq" {
  for_each                  = toset(var.categories)
  name                      = "${var.name_prefix}-${each.value}-dlq"
  message_retention_seconds = 1209600 # 14 days — keep poison messages for triage
  kms_master_key_id         = var.kms_key_arn
  tags                      = var.tags
}

resource "aws_sqs_queue" "main" {
  for_each                   = toset(var.categories)
  name                       = "${var.name_prefix}-${each.value}"
  visibility_timeout_seconds = 300 # ≥ the slowest handler (re-embed); avoids premature redelivery
  kms_master_key_id          = var.kms_key_arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })
  tags = var.tags
}

# All queue ARNs (main + dlq) — fed to the IAM module for exact-ARN scoping.
output "queue_arns" {
  value = concat(
    [for q in aws_sqs_queue.main : q.arn],
    [for q in aws_sqs_queue.dlq : q.arn],
  )
}
output "queue_urls" { value = { for k, q in aws_sqs_queue.main : k => q.url } }
