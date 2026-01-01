terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration - values provided via backend.hcl
  # Run: cd infrastructure && just init-dev
  # Or manually: terraform init -backend-config=backend.hcl
  backend "s3" {
    # All values provided by backend.hcl (auto-generated from bootstrap outputs)
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Automatically fetch AWS account info
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# DynamoDB tables
module "dynamodb" {
  source = "../../modules/dynamodb"

  project_name      = var.project_name
  environment       = var.environment
  account_id        = local.account_id
  traces_table_name = var.traces_table_name
  spans_table_name  = var.spans_table_name
  enable_pitr       = false # Disabled for dev (cost savings)
}

# Lambda function (uses pre-created role from bootstrap)
module "lambda" {
  source = "../../modules/lambda"

  project_name           = var.project_name
  environment            = var.environment
  account_id             = local.account_id
  aws_region             = var.aws_region
  lambda_role_arn        = var.lambda_role_arn # From bootstrap output!
  traces_table_name      = module.dynamodb.traces_table_name
  spans_table_name       = module.dynamodb.spans_table_name
  lambda_package_path    = var.lambda_package_path
  lambda_memory_mb       = var.lambda_memory_mb
  lambda_timeout_seconds = var.lambda_timeout_seconds
  cors_origins           = "*"
  api_keys               = var.api_keys
  api_key_required       = "true"
  default_project_key    = var.default_project_key
  rate_limit_rpm         = 100
  log_retention_days     = 3 # Short retention for dev
}

# Monitoring
module "monitoring" {
  source = "../../modules/monitoring"

  project_name           = var.project_name
  environment            = var.environment
  enable_cost_alerts     = true
  monthly_budget_limit   = 5 # $5/month for dev
  alert_email_addresses  = var.alert_emails
  lambda_function_name   = module.lambda.function_name
  traces_table_name      = module.dynamodb.traces_table_name
  enable_error_alerts    = false # Disabled for dev
  enable_dynamodb_alerts = false # Disabled for dev
}

