variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "llm-tracer"
}

variable "environment" {
  description = "Environment"
  type        = string
  default     = "dev"
}

variable "traces_table_name" {
  description = "DynamoDB Traces table name (leave null for auto-generate)"
  type        = string
  default     = null
}

variable "spans_table_name" {
  description = "DynamoDB Spans table name (leave null for auto-generate)"
  type        = string
  default     = null
}

variable "lambda_role_arn" {
  description = "ARN for lambda execution role (precreated with bootstrap)"
  type        = string
}

variable "lambda_package_path" {
  description = "Path to lambda deployment package"
  type        = string
  default     = "../../../service/dist/lambda.zip"
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB"
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "api_keys" {
  description = "Valid api keys (comma separated, format: project-{project_id})"
  type        = string
  sensitive   = true
}

variable "default_project_key" {
  description = "Default project key when auth is disabled"
  type        = string
  default     = "project-public"
}

variable "alert_emails" {
  description = "Email addresses for alerts"
  type        = list(string)
  default     = []
}
