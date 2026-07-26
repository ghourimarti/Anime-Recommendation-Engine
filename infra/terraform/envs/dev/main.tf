# dev environment composition. Wires the generic modules with dev-sized
# inputs. Module ORDER here is implicit via output→input references, which is also
# the dependency graph: vpc → secrets → eks → {rds, elasticache, sqs, s3, ecr} → iam.

module "vpc" {
  source             = "../../modules/vpc"
  name               = var.name_prefix
  cidr               = "10.0.0.0/16"
  az_count           = 2
  single_nat_gateway = true # dev: one NAT (cost). prod: false.
}

module "secrets" {
  source      = "../../modules/secrets"
  name_prefix = var.name_prefix
}

module "eks" {
  source              = "../../modules/eks"
  name                = var.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  node_instance_types = ["t3.medium"] # dev sizing
  node_desired_size   = 2
  node_min_size       = 2
  node_max_size       = 5
  public_access_cidrs = var.eks_public_access_cidrs
}

module "rds" {
  source                     = "../../modules/rds"
  name                       = var.name_prefix
  vpc_id                     = module.vpc.vpc_id
  subnet_ids                 = module.vpc.private_subnet_ids
  ingress_security_group_ids = [module.eks.node_security_group_id]
  kms_key_arn                = module.secrets.kms_key_arn
  instance_class             = "db.t4g.small"
  multi_az                   = false # dev
}

module "elasticache" {
  source                     = "../../modules/elasticache"
  name                       = var.name_prefix
  vpc_id                     = module.vpc.vpc_id
  subnet_ids                 = module.vpc.private_subnet_ids
  ingress_security_group_ids = [module.eks.node_security_group_id]
  node_type                  = "cache.t4g.micro"
  multi_az                   = false # dev
}

module "sqs" {
  source      = "../../modules/sqs"
  name_prefix = var.name_prefix
  kms_key_arn = module.secrets.kms_key_arn
}

module "s3" {
  source      = "../../modules/s3"
  name_prefix = var.name_prefix
  kms_key_arn = module.secrets.kms_key_arn
}

module "ecr" {
  source      = "../../modules/ecr"
  name_prefix = "anime-recommender" # ECR repos are account-wide, not per-env
}

module "iam" {
  source            = "../../modules/iam"
  name_prefix       = var.name_prefix
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  sqs_queue_arns    = module.sqs.queue_arns
  s3_bucket_arns    = module.s3.bucket_arns
  secret_arns       = module.secrets.secret_arns
}

module "monitoring" {
  source             = "../../modules/monitoring"
  name_prefix        = var.name_prefix
  monthly_budget_usd = 300 # target: < $300/mo @ 10k MAU
  alert_emails       = var.alert_emails
}
