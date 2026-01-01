# Lambda function for LLM tracer API
# Note: This module uses a PRE-created IAM role from bootstrap
# This is a security feature - the dev user cannot create IAM roles

# Naming prefix
locals {
  name_prefix = "${var.project_name}-${var.account_id}-${var.environment}"
}

# Lambda function (uses pre-created role via PassRole)
resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = var.lambda_role_arn # Pre created in bootstrap!

  # Deployment package
  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  # Runtime configuration
  handler = "lambda_handler.handler"
  runtime = "python3.12"

  # Performance configuration
  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  # Environment variables
  # Note: AWS_REGION is automatically set by Lambda runtime
  environment {
    variables = {
      DYNAMODB_TRACES_TABLE = var.traces_table_name
      DYNAMODB_SPANS_TABLE  = var.spans_table_name
      LOG_LEVEL             = var.log_level
      CORS_ORIGINS          = var.cors_origins
      API_KEYS              = var.api_keys
      API_KEY_REQUIRED      = var.api_key_required
      RATE_LIMIT_RPM        = var.rate_limit_rpm
      DEFAULT_PROJECT_KEY   = var.default_project_key
    }
  }

  tags = {
    Name        = "${local.name_prefix}-api"
    Environment = var.environment
  }
}

# Lambda Function URL (simpler than API Gateway for private use)
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # API key handled in application

  cors {
    allow_origins = split(",", var.cors_origins)
    allow_methods = ["*"]
    allow_headers = ["*"]
    max_age       = 86400
  }
}

# Resource-based policy to allow public access to Function URL
# IMPORTANT: Even with authorization_type = "NONE" on the Function URL,
# you still need this aws_lambda_permission resource. Without it, callers
# get a 403 Forbidden error. The Function URL auth type only controls
# whether AWS IAM signing is required - the resource policy controls
# who can actually invoke the function.
# See: https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html
resource "aws_lambda_permission" "function_url_public" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# Second permission required for Function URL invocation
resource "aws_lambda_permission" "function_url_invoke" {
  statement_id  = "FunctionURLAllowPublicInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "*"
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${local.name_prefix}-lambda-logs"
    Environment = var.environment
  }
}