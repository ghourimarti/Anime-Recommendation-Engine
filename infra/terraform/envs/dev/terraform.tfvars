# dev environment values. (staging/prod get their own envs/ dir with
# the deltas noted in docs/runbooks/terraform-apply.md: bigger nodes, multi-AZ
# RDS/Redis, single_nat_gateway=false, public_access_cidrs locked down.)

region      = "us-east-1"
name_prefix = "anime-dev"

# Billing-alert recipients. Fill before apply.
alert_emails = []

# Lock the EKS public API endpoint to your IP/VPN CIDR(s). Empty = private-only
# (you'd then reach the cluster via a bastion / VPN). Example: ["203.0.113.4/32"]
eks_public_access_cidrs = []
