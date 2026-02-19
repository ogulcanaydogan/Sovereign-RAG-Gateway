# ---------------------------------------------------------------------------
# Required variables
# ---------------------------------------------------------------------------

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for EKS secrets encryption at rest"
  type        = string
}

variable "srg_api_keys" {
  description = "Comma-separated API keys for the gateway (sensitive)"
  type        = string
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to use"
  type        = number
  default     = 2
}

variable "public_api_access" {
  description = "Enable public access to the EKS API endpoint"
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# EKS Cluster
# ---------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

# ---------------------------------------------------------------------------
# Node Group
# ---------------------------------------------------------------------------

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 4
}

variable "node_disk_size_gb" {
  description = "Disk size in GB for each worker node"
  type        = number
  default     = 50
}

# ---------------------------------------------------------------------------
# Gateway Helm release
# ---------------------------------------------------------------------------

variable "gateway_namespace" {
  description = "Kubernetes namespace for the gateway"
  type        = string
  default     = "sovereign-rag"
}

variable "gateway_chart_version" {
  description = "Helm chart version"
  type        = string
  default     = "0.4.0-rc1"
}

variable "gateway_image_tag" {
  description = "Container image tag for the gateway"
  type        = string
  default     = "v0.4.0-rc1"
}

variable "gateway_replicas" {
  description = "Number of gateway replicas"
  type        = number
  default     = 2
}

variable "srg_provider_name" {
  description = "Primary LLM provider name"
  type        = string
  default     = "stub"
}

variable "srg_budget_enabled" {
  description = "Enable in-path token budget enforcement"
  type        = bool
  default     = false
}

variable "srg_budget_backend" {
  description = "Budget backend implementation (memory or redis)"
  type        = string
  default     = "memory"
}

variable "srg_budget_redis_url" {
  description = "Redis URL for distributed budget tracking (when backend=redis)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "srg_webhook_enabled" {
  description = "Enable webhook notifications"
  type        = bool
  default     = false
}

variable "srg_tracing_enabled" {
  description = "Enable request-level tracing"
  type        = bool
  default     = false
}

variable "srg_tracing_otlp_enabled" {
  description = "Enable OTLP/HTTP exporter for traces"
  type        = bool
  default     = false
}

variable "srg_tracing_otlp_endpoint" {
  description = "OTLP/HTTP trace endpoint (e.g. http://otel-collector:4318/v1/traces)"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

variable "tags" {
  description = "Resource tags applied to all infrastructure"
  type        = map(string)
  default = {
    Project     = "sovereign-rag-gateway"
    ManagedBy   = "terraform"
    Environment = "production"
  }
}
