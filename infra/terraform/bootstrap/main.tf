# Remote-state bootstrap.
#
# State is itself infrastructure — the S3 backend can't define its own bucket.
# So this tiny config is applied ONCE with a LOCAL backend to create the state
# bucket + DynamoDB lock table; every other env then uses them as its backend.
#
#   cd infra/terraform/bootstrap && terraform init && terraform apply
#
# Run once per AWS account. Output the names into each env's backend.tf.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally-unique S3 bucket for Terraform state."
  default     = "anime-recommender-tfstate"
}

variable "lock_table_name" {
  type    = string
  default = "anime-recommender-tflock"
}

provider "aws" {
  region = var.region
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
  # Prevent fat-finger deletion of the bucket holding all infra state.
  lifecycle {
    prevent_destroy = true
  }
}

# Versioning = recover a corrupted/last-good state file.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# State can contain secrets in plaintext — never expose the bucket.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB lock table prevents two `terraform apply`s from racing on the state.
resource "aws_dynamodb_table" "lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket" {
  value = aws_s3_bucket.state.id
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}
