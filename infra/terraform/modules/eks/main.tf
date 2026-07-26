# EKS module — managed cluster + node group + OIDC (IRSA).

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets for the nodes."
}
variable "kubernetes_version" {
  type    = string
  default = "1.31"
}
variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"] # dev. prod tfvars: ["m6i.large"].
}
variable "node_desired_size" {
  type    = number
  default = 2
}
variable "node_min_size" {
  type    = number
  default = 2
}
variable "node_max_size" {
  type    = number
  default = 5
}
variable "public_access_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to reach the public API endpoint. Empty → private-only."
}
variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_partition" "current" {}

# ── Cluster IAM role ──────────────────────────────────────────────────────────
resource "aws_iam_role" "cluster" {
  name = "${var.name}-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "this" {
  name     = var.name
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_private_access = true
    # Public endpoint locked to an allowlist; empty list → private-only access.
    endpoint_public_access = length(var.public_access_cidrs) > 0
    public_access_cidrs    = var.public_access_cidrs
  }

  # Ship control-plane logs to CloudWatch (audit + api are the useful ones).
  enabled_cluster_log_types = ["api", "audit", "authenticator"]

  depends_on = [aws_iam_role_policy_attachment.cluster]
  tags       = var.tags
}

# ── OIDC provider — the IRSA enabler (pods assume IAM roles via a SA token) ─────
data "tls_certificate" "oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "this" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
  tags            = var.tags
}

# ── Node group ──────────────────────────────────────────────────────────────
resource "aws_iam_role" "node" {
  name = "${var.name}-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "AmazonEKSWorkerNodePolicy",
    "AmazonEKS_CNI_Policy",
    "AmazonEC2ContainerRegistryReadOnly",
  ])
  role       = aws_iam_role.node.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/${each.value}"
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name}-ng"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.subnet_ids
  instance_types  = var.node_instance_types

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }
  update_config {
    max_unavailable = 1
  }
  depends_on = [aws_iam_role_policy_attachment.node]
  tags       = var.tags
}

output "cluster_name" { value = aws_eks_cluster.this.name }
output "cluster_endpoint" { value = aws_eks_cluster.this.endpoint }
output "cluster_ca" { value = aws_eks_cluster.this.certificate_authority[0].data }
output "oidc_provider_arn" { value = aws_iam_openid_connect_provider.this.arn }
output "oidc_provider_url" { value = replace(aws_iam_openid_connect_provider.this.url, "https://", "") }
output "node_security_group_id" { value = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id }
