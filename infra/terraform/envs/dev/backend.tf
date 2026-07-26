# Remote state backend → the bucket + lock table created by ../../bootstrap.
# `terraform init` wires this. (Validation runs with -backend=false, so this is
# inert until a real `init` against AWS.)
terraform {
  backend "s3" {
    bucket         = "anime-recommender-tfstate"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "anime-recommender-tflock"
    encrypt        = true
  }
}
