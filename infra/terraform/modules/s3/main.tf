# S3 module — artifacts + backups buckets, KMS, locked down.

variable "name_prefix" { type = string }
variable "kms_key_arn" { type = string }
variable "buckets" {
  type    = list(string)
  default = ["artifacts", "backups"]
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_s3_bucket" "this" {
  for_each = toset(var.buckets)
  bucket   = "${var.name_prefix}-${each.value}"
  tags     = var.tags
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true # cuts KMS request cost on high-volume buckets
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: expire old versions; tier cold backups to cheaper storage.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 90 }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

output "bucket_arns" { value = [for b in aws_s3_bucket.this : b.arn] }
output "bucket_names" { value = { for k, b in aws_s3_bucket.this : k => b.id } }
