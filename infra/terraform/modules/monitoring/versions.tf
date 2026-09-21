# Provider + Terraform constraints for this module.
#
# tflint flagged every module for missing these (terraform_required_providers,
# terraform_required_version). It matters because a module without constraints
# silently inherits whatever the root happens to pin: it works until someone
# reuses it under a different root, and then fails on a provider schema change
# with no indication that a version was ever the contract.
#
# Constraints match envs/dev deliberately — same repo, one provider generation.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    # slack.tf zips the Lambda source with data "archive_file". Missed on the first
    # pass because the detection only looked for tls_ prefixes — a reminder that
    # "which providers does this module use" is a question to answer by reading the
    # linter's output, not by pattern-matching what you expect to find.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}
