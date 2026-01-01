variable "project_name" {
  description = "Project name (used in resource names)"
  type        = string
}

variable "environment" {
  description = "Environment (used in resource names)"
  type        = string
}

variable "enable_cost_alerts" {
  description = "Enable cost budget alerts"
  type        = bool
  default     = true
}

variable "monthly_budget_limit" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 10
}

variable "alert_email_addresses" {
  description = "Email addresses to receive budget alerts"
  type        = list(string)
  default     = []
}

variable "enable_error_alerts" {
  description = "Enable Lambda error alerts"
  type        = bool
  default     = true
}

variable "enable_dynamodb_alerts" {
  description = "Enable DynamoDB throttle alerts"
  type        = bool
  default     = true
}

variable "lambda_function_name" {
  description = "Name of the Lambda function to monitor for errors"
  type        = string
}

variable "traces_table_name" {
  description = "DynamoDB table name for traces"
  type        = string
}

# SNS - simple Notification Service
variable "sns_topic_arn" {
  description = "ARN of the SNS topic for alerts"
  type        = string
  default     = null
}