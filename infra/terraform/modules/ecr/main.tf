# ECR module — one repo per image, scan-on-push + lifecycle.

variable "name_prefix" { type = string }
variable "repositories" {
  type    = list(string)
  default = ["api", "web", "worker"]
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_ecr_repository" "this" {
  for_each             = toset(var.repositories)
  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = "IMMUTABLE" # tags can't be overwritten → reproducible deploys
  image_scanning_configuration {
    scan_on_push = true # CVE scan every push (complements the Trivy scan in CI)
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
  tags = var.tags
}

# Expire untagged + keep only the last N tagged images → bounded storage cost.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the last 20 tagged images"
        selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
        action       = { type = "expire" }
      },
    ]
  })
}

output "repository_urls" { value = { for k, r in aws_ecr_repository.this : k => r.repository_url } }
