# Runbook — Terraform apply

The infra is **authored** but not yet applied. This is the apply sequence.
**Order matters** — state bootstrap is a one-time prerequisite.

## 0. Prereqs
- AWS creds with admin-ish perms for the target account (`aws sts get-caller-identity`).
- `terraform >= 1.6`. Optional: `tflint`, `tfsec`.
- A budget you accept: EKS control plane alone is ~$73/mo; NAT + RDS + nodes add more.

## 1. Bootstrap remote state (ONCE per account)
```bash
cd infra/terraform/bootstrap
terraform init          # local backend
terraform apply         # creates the state bucket + lock table
```
The bucket/table names must match `envs/dev/backend.tf`.

## 2. Lint + security scan (no AWS calls)
```bash
cd infra/terraform
terraform fmt -recursive -check
tflint --init && tflint --recursive
tfsec .
```

## 3. Plan the dev env (READ-ONLY — the pre-apply gate)
```bash
cd infra/terraform/envs/dev
terraform init                      # wires the S3 backend
terraform plan -out dev.tfplan      # REVIEW every create. No surprises = gate pass.
```

## 4. Apply dev
```bash
terraform apply dev.tfplan
terraform output                    # cluster_name, rds_endpoint, IRSA ARNs, ECR URLs
```
Then set the real secret values (placeholders → real):
```bash
aws secretsmanager put-secret-value --secret-id anime-dev/openai --secret-string '{"value":"sk-..."}'
# repeat for groq / clerk / langfuse
```
RDS master password is RDS-managed (see `rds_master_secret_arn`).

## 5. staging / prod (deltas, added as envs/staging|prod later)
Same modules; tfvars differences:
| knob | dev | prod |
|---|---|---|
| `single_nat_gateway` (vpc) | true | false (one NAT/AZ, HA) |
| `node_instance_types` (eks) | t3.medium | m6i.large |
| `multi_az` (rds, elasticache) | false | true |
| `eks_public_access_cidrs` | your IP | tightly locked / private-only |
| backend `key` | dev/… | prod/… (separate state) |

## Teardown (dev)
```bash
cd infra/terraform/envs/dev && terraform destroy
```
Note: RDS has `deletion_protection = true` and S3 state bucket has
`prevent_destroy` — both require an explicit override to remove.
```
```
