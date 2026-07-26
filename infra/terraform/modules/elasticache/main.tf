# ElastiCache Redis module — private, encrypted.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "ingress_security_group_ids" { type = list(string) }
variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}
variable "multi_az" {
  type    = bool
  default = false
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name}-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.name}-redis-sg"
  description = "Redis access from app nodes only"
  vpc_id      = var.vpc_id
  ingress {
    description     = "Redis from app nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.ingress_security_group_ids
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = var.name
  description                = "Anime recommender cache"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.node_type
  num_cache_clusters         = var.multi_az ? 2 : 1
  automatic_failover_enabled = var.multi_az
  multi_az_enabled           = var.multi_az
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.this.id]
  # Encryption on even in dev — parity with prod, cheap, and tfsec-clean.
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  # LRU eviction: it's a cache, never let it OOM (mirrors the docker-compose config).
  parameter_group_name = aws_elasticache_parameter_group.this.name
  tags                 = var.tags
}

resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name}-redis7"
  family = "redis7"
  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }
  tags = var.tags
}

output "primary_endpoint" { value = aws_elasticache_replication_group.this.primary_endpoint_address }
output "security_group_id" { value = aws_security_group.this.id }
