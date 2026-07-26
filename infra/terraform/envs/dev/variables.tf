variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "anime-dev"
}

variable "alert_emails" {
  type        = list(string)
  default     = []
  description = "Billing-alert subscribers. Set in terraform.tfvars."
}

variable "eks_public_access_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to hit the EKS public API endpoint (your office/VPN). Empty → private-only."
}
