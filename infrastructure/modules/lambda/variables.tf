variable "project_name" {
  description = "Project name (used in resource names)"
  type        = string
}

variable "environment" {
  description = "Environment (used in resource names)"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID (used in resource names)"
  type        = string
}

variable "aws_region" {
  description = "AWS region (used in resource names)"
  type        = string
}

variable "lambda_role_arn" {
  description = "Lambda role ARN (used in resource names)"
  type        = string
}

variable "traces_table_name" {
  description = "Traces table name (used in resource names)"
  type        = string
}

variable "spans_table_name" {
  description = "Spans table name (used in resource names)"
  type        = string
}

variable "lambda_package_path" {
  description = "Path to Lmabda deployment package (zip file)"
  type        = string
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

variable "log_level" {
  description = "Log level (DEBUG, INFO, WARNING, ERROR)"
  type        = string
  default     = "INFO"
}

variable "cors_origins" {
  description = "List of allowed CORS origins (comma separated)"
  type        = string
  default     = "*"
}

variable "api_keys" {
  description = "Valid API keys for authentication (comma separated, format: project-{project_id})"
  type        = string
  sensitive   = true
}

variable "api_key_required" {
  description = "Require API key for authentication"
  type        = string
  default     = "true"
}

variable "default_project_key" {
  description = "Default project key when auth is disabled"
  type        = string
  default     = "project-public"
}

variable "rate_limit_rpm" {
  description = "Rate limit in requests per minute"
  type        = number
  default     = 100 # in python code the buffer is anyway set to 60 through a custom script
}

variable "log_retention_days" {
  description = "Cloudwatch log retention in days"
  type        = number
  default     = 7
}
