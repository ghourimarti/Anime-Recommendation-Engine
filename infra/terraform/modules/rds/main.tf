# RDS Postgres module — pgvector-capable, private, encrypted.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "ingress_security_group_ids" {
  type        = list(string)
  description = "SGs allowed to reach Postgres (the EKS node SG)."
}
variable "kms_key_arn" { type = string }
variable "instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "allocated_storage" {
  type    = number
  default = 20
}
variable "multi_az" {
  type    = bool
  default = false # dev: single-AZ. prod tfvars: true.
}
variable "db_name" {
  type    = string
  default = "anime"
}
variable "master_username" {
  type    = string
  default = "anime"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.name}-rds-sg"
  description = "Postgres access from app nodes only"
  vpc_id      = var.vpc_id
  ingress {
    description     = "Postgres from app nodes"
    from_port       = 5432
    to_port         = 5432
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

# pgvector ships with RDS Postgres 16; CREATE EXTENSION is run by the migration
# (0001_initial). A custom parameter group is the seam for future tuning.
resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-pg16"
  family = "postgres16"
  tags   = var.tags
}

# Master password is generated and stored in Secrets Manager by the secrets
# module — NOT set here (it would land in state). manage_master_user_password
# lets RDS own the secret + rotation natively.
resource "aws_db_instance" "this" {
  identifier                   = var.name
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.instance_class
  allocated_storage            = var.allocated_storage
  max_allocated_storage        = var.allocated_storage * 5 # storage autoscaling
  db_name                      = var.db_name
  username                     = var.master_username
  manage_master_user_password  = true # RDS-managed secret + rotation
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.this.id]
  parameter_group_name         = aws_db_parameter_group.this.name
  multi_az                     = var.multi_az
  storage_encrypted            = true
  kms_key_id                   = var.kms_key_arn
  backup_retention_period      = 7 # PITR window (RPO < 5min via continuous backups)
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "${var.name}-final"
  publicly_accessible          = false # private subnets + SG only
  performance_insights_enabled = true
  tags                         = var.tags
}

output "endpoint" { value = aws_db_instance.this.address }
output "port" { value = aws_db_instance.this.port }
output "security_group_id" { value = aws_security_group.this.id }
output "master_secret_arn" { value = aws_db_instance.this.master_user_secret[0].secret_arn }
