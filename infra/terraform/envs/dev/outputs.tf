# Outputs consumed by the deploy step: kubeconfig wiring, the
# DB/Redis endpoints injected into the app's secret, IRSA role ARNs for the
# ServiceAccount annotations, ECR push targets.

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "rds_endpoint" { value = module.rds.endpoint }
output "redis_endpoint" { value = module.elasticache.primary_endpoint }
output "api_irsa_role_arn" { value = module.iam.api_role_arn }
output "worker_irsa_role_arn" { value = module.iam.worker_role_arn }
output "ecr_repository_urls" { value = module.ecr.repository_urls }
output "sqs_queue_urls" { value = module.sqs.queue_urls }
output "rds_master_secret_arn" {
  value     = module.rds.master_secret_arn
  sensitive = true
}
