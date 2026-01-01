variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID (for unique resource naming)"
  type        = string
}

variable "traces_table_name" {
  description = "Name of the traces table"
  type        = string
  default     = null
  # mainly to detect if null, then do something programatically
  # like for example, create a default table name
}

variable "spans_table_name" {
  description = "Name of the spans table"
  type        = string
  default     = null
}

variable "enable_pitr" {
  description = "Enable Point-in-Time Recovery (PITR) for DynamoDB tables"
  type        = bool
  default     = false
}

locals {
  # Naming: project-accountid-env-resource 
  # (e.g., llm-tracer-123456789012-dev-traces)
  name_prefix       = "${var.project_name}-${var.account_id}-${var.environment}"
  traces_table_name = var.traces_table_name != null ? var.traces_table_name : "${local.name_prefix}-traces"
  spans_table_name  = var.spans_table_name != null ? var.spans_table_name : "${local.name_prefix}-spans"
}
