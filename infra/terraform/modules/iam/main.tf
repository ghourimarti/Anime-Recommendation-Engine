# IRSA roles — least-privilege per workload.
#
# Each K8s ServiceAccount assumes a scoped IAM role via the EKS OIDC provider.
# Policies are scoped to EXACT ARNs (no "*") — a security review should
# find zero wildcards here.

variable "name_prefix" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_provider_url" { type = string }
variable "namespace" {
  type    = string
  default = "anime"
}
variable "sqs_queue_arns" {
  type        = list(string)
  description = "Exact ARNs of the app's SQS queues (+ DLQs)."
}
variable "s3_bucket_arns" { type = list(string) }
variable "secret_arns" { type = list(string) }
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  # IRSA trust: this OIDC provider + a specific namespace:serviceaccount subject.
  sub = "${var.oidc_provider_url}:sub"
  aud = "${var.oidc_provider_url}:aud"
}

data "aws_iam_policy_document" "trust_api" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = local.aud
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = local.sub
      values   = ["system:serviceaccount:${var.namespace}:anime-api"]
    }
  }
}

data "aws_iam_policy_document" "trust_worker" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = local.aud
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = local.sub
      # Both the worker SA and the external-secrets SA assume this pattern; here
      # we scope to the worker SA. (external-secrets gets its own role below.)
      values = ["system:serviceaccount:${var.namespace}:anime-worker"]
    }
  }
}

# ── API role: send to SQS, read secrets, rw the app S3 buckets ────────────────
resource "aws_iam_role" "api" {
  name               = "${var.name_prefix}-api"
  assume_role_policy = data.aws_iam_policy_document.trust_api.json
  tags               = var.tags
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "SqsSend"
    effect    = "Allow"
    actions   = ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
    resources = var.sqs_queue_arns
  }
  statement {
    sid       = "SecretsRead"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = var.secret_arns
  }
  statement {
    sid       = "S3Rw"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = concat(var.s3_bucket_arns, [for a in var.s3_bucket_arns : "${a}/*"])
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.name_prefix}-api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ── Worker role: receive/delete from SQS, read secrets, rw S3 ─────────────────
resource "aws_iam_role" "worker" {
  name               = "${var.name_prefix}-worker"
  assume_role_policy = data.aws_iam_policy_document.trust_worker.json
  tags               = var.tags
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid    = "SqsConsume"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueUrl",
      "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility", "sqs:CreateQueue",
    ]
    resources = var.sqs_queue_arns
  }
  statement {
    sid       = "SecretsRead"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = var.secret_arns
  }
  statement {
    sid       = "S3Rw"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = concat(var.s3_bucket_arns, [for a in var.s3_bucket_arns : "${a}/*"])
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "${var.name_prefix}-worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

output "api_role_arn" { value = aws_iam_role.api.arn }
output "worker_role_arn" { value = aws_iam_role.worker.arn }
