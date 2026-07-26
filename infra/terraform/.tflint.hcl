# tflint config. Runs in CI + locally:
#   cd infra/terraform && tflint --init && tflint --recursive
# The AWS ruleset catches deprecated args, invalid instance types, missing tags.

config {
  call_module_type = "all"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
