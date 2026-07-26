# Secrets + KMS module.
#
# A KMS key for envelope encryption (RDS, S3, secrets) + Secrets Manager secrets
# as PLACEHOLDERS. Real values are set out-of-band (CLI/console/CI) so they never
# land in HCL/tfvars/state. The provider keys (OpenAI/Groq/Clerk/Langfuse) are
# created empty here; the External Secrets Operator syncs them into K8s.

variable "name_prefix" { type = string }
variable "secret_names" {
  type    = list(string)
  default = ["openai", "groq", "clerk", "langfuse"]
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} envelope encryption (RDS/S3/secrets)"
  deletion_window_in_days = 14
  enable_key_rotation     = true # annual automatic rotation
  tags                    = var.tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

resource "aws_secretsmanager_secret" "app" {
  for_each   = toset(var.secret_names)
  name       = "${var.name_prefix}/${each.value}"
  kms_key_id = aws_kms_key.this.arn
  tags       = var.tags
}

# Placeholder version — real value set out-of-band. ignore_changes means a later
# `terraform apply` won't clobber the real value someone put in via the CLI.
resource "aws_secretsmanager_secret_version" "app" {
  for_each      = aws_secretsmanager_secret.app
  secret_id     = each.value.id
  secret_string = jsonencode({ value = "REPLACE_ME" })
  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "kms_key_arn" { value = aws_kms_key.this.arn }
output "secret_arns" { value = [for s in aws_secretsmanager_secret.app : s.arn] }
