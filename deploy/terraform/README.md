# Terraform EKS Reference Module

This module provisions a production-oriented baseline for Sovereign RAG Gateway on AWS:

- VPC with public/private subnets and per-AZ NAT gateways
- EKS control plane + managed node group
- Helm deployment of the gateway into a dedicated namespace
- EKS secrets encryption at rest
- EKS control-plane audit logs enabled

## Required Inputs

| Variable | Type | Description |
|---|---|---|
| `cluster_name` | `string` | EKS cluster name |
| `kms_key_arn` | `string` | KMS key ARN for EKS secret encryption |
| `srg_api_keys` | `string` | Comma-separated gateway API keys (sensitive) |

## Key Optional Inputs

| Variable | Default | Description |
|---|---|---|
| `kubernetes_version` | `1.29` | EKS Kubernetes version |
| `gateway_chart_version` | `0.6.0-alpha.1` | Helm chart/app release version |
| `gateway_image_tag` | `v0.6.0-alpha.1` | Gateway image tag |
| `gateway_replicas` | `2` | Gateway replica count |
| `public_api_access` | `false` | Public EKS API endpoint access |
| `srg_budget_enabled` | `false` | Enables budget enforcement in gateway |
| `srg_budget_backend` | `memory` | Budget backend (`memory` or `redis`) |
| `srg_budget_redis_url` | `""` | Redis DSN used when backend is `redis` |
| `srg_webhook_enabled` | `false` | Enables webhook notifications |
| `srg_webhook_dead_letter_backend` | `sqlite` | Webhook dead-letter backend (`sqlite` or `jsonl`) |
| `srg_webhook_dead_letter_path` | `/tmp/audit/webhook_dead_letter.db` | Dead-letter storage path |
| `srg_webhook_dead_letter_retention_days` | `30` | Dead-letter retention period |
| `srg_tracing_enabled` | `false` | Enables request trace collection |
| `srg_tracing_otlp_enabled` | `false` | Enables OTLP exporter |
| `srg_tracing_otlp_endpoint` | `""` | OTLP collector endpoint |

## Minimal `terraform.tfvars` Example

```hcl
cluster_name   = "srg-prod"
kms_key_arn    = "arn:aws:kms:us-east-1:123456789012:key/abcd-1234"
srg_api_keys   = "prod-key-1,prod-key-2"

gateway_image_tag    = "v0.6.0-alpha.1"
gateway_chart_version = "0.6.0-alpha.1"
gateway_replicas     = 3
srg_budget_enabled   = true
srg_budget_backend   = "memory"
srg_webhook_enabled  = true
srg_webhook_dead_letter_backend = "sqlite"
srg_webhook_dead_letter_retention_days = 30
srg_tracing_enabled  = true

tags = {
  Project     = "sovereign-rag-gateway"
  Environment = "production"
  ManagedBy   = "terraform"
}
```

## Usage

```bash
cd deploy/terraform
terraform init
terraform fmt -check
terraform validate
terraform plan -out tfplan
```

## Secure Defaults

- `public_api_access=false` for private cluster API exposure by default.
- EKS secret encryption is mandatory (`kms_key_arn` required).
- EKS control-plane logs include `audit`.
- Provider keys are passed via `set_sensitive` in Helm release configuration.

## Outputs

Notable outputs:

- `cluster_endpoint`
- `cluster_name`
- `cluster_version`
- `vpc_id`
- `private_subnet_ids`
- `gateway_namespace`
- `region`
