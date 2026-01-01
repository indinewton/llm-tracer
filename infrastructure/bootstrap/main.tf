# Bootstrap resources for Terraform state management
# Run this ONCE with "admin" like credentials before using main Terraform configs
# This creates: State bucket, Lambda Role, Dev User (with restricted permissions)

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "llm-tracer"
      ManagedBy   = "terraform"
      Environment = "bootstrap"
    }
  }
}

variable "aws_region" {
  description = "AWS region for backend resources"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Project name (used in resource names)"
  type        = string
  default     = "llm-tracer"
}

# Automatically fetch AWS account info
data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  name_prefix = "${var.project_name}-${local.account_id}"
}

# ========================================================
# Terraform State bucket
# ========================================================

# S3 bucket for Terraform state
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${local.name_prefix}-terraform-state"

  tags = {
    Name      = "Terraform State Bucket"
    AccountId = local.account_id
  }
}

# Enable versioning for state history
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${local.name_prefix}-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
  tags = {
    Name      = "Terraform State Lock Table"
    AccountId = local.account_id
  }
}

# ========================================================
# Lambda Execution Role (pre-created for security)
# ========================================================

# IAM role that Lambda will assume
resource "aws_iam_role" "lambda_execution" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  tags = {
    Name = "${local.name_prefix}-lambda-role"
  }
}

# Policy for lambda to access DynamoDB
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "dynamodb-access"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = [
          "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${local.name_prefix}-*",
          "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${local.name_prefix}-*/index/*"
        ]
      }
    ]
  })
}

# Attach basic lambda execution policy (cloudwatch logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ========================================================
# Dev User (created manually -Not managed by Terraform)
# ========================================================

# The following resources were created MANUALLY via AWS Console:
# - IAM user: llm-tracer-dev
# - IAM policy: LLMTracerDeploymentPolicy
# - Policy attachment to user
# - Access keys for the user
#
# This keeps the dev user outside of Terraform state, which is intentional:
# - Bootstrap can be re-run without affecting dev credentials
# - Dev user lifecycle is managed separately
# ========================================================

# ========================================================
# Output values for use in main Terraform configs
# ========================================================

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "account_id" {
  description = "AWS Account ID (used in resource naming)"
  value       = local.account_id
}

output "name_prefix" {
  description = "Name prefix for all resources"
  value       = local.name_prefix
}

output "s3_bucket_name" {
  description = "Terraform state bucket name"
  value       = aws_s3_bucket.terraform_state.id
}

output "dynamodb_table_name" {
  description = "Terraform state lock DynamoDB table name"
  value       = aws_dynamodb_table.terraform_locks.name
}

output "lambda_role_name" {
  description = "Lambda execution role name"
  value       = aws_iam_role.lambda_execution.name
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda_execution.arn
}

output "setup_instructions" {
  description = "Next steos after bootstrap (MAKE SURE TO RUN BOOTSTRAP ONLY ONCE)"
  value       = <<-EOT
      ========================================
  BOOTSTRAP COMPLETE!
  ========================================

  Your AWS Account ID: ${local.account_id}

  1. Configure AWS CLI with your manually created llm-tracer-dev credentials:
     aws configure --profile llm-tracer
     # Enter the access keys you created for llm-tracer-dev

  2. Update backend config in environments/dev/main.tf:
     Replace ACCOUNT_ID with: ${local.account_id}

     backend "s3" {
       bucket         = "${aws_s3_bucket.terraform_state.id}"
       key            = "dev/terraform.tfstate"
       region         = "${var.aws_region}"
       dynamodb_table = "${aws_dynamodb_table.terraform_locks.name}"
       encrypt        = true
     }

  3. Lambda Role ARN (use in Lambda module):
     ${aws_iam_role.lambda_execution.arn}

  EOT
}
