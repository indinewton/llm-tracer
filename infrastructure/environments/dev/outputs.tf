output "account_id" {
  description = "AWS Account ID"
  value       = local.account_id
}

output "api_url" {
  description = "API URL (Lambda Function URL)"
  value       = module.lambda.function_url
}

output "traces_table_name" {
  description = "DynamoDB Traces table name"
  value       = module.dynamodb.traces_table_name
}

output "spans_table_name" {
  description = "DynamoDB Spans table name"
  value       = module.dynamodb.spans_table_name
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.lambda.function_name
}

output "configuration" {
  description = "Environment configuration for .env file"
  value       = <<-EOT

    AWS Account ID: ${local.account_id}

    # Add to your .env file
    TRACER_URL=${module.lambda.function_url}
    TRACER_API_KEYS=${nonsensitive(var.api_keys)}
    TRACER_PROJECT_ID=dev
    DYNAMODB_TRACES_TABLE=${module.dynamodb.traces_table_name}
    DYNAMODB_SPANS_TABLE=${module.dynamodb.spans_table_name}
    AWS_REGION=${var.aws_region}
    EOT
  sensitive   = false
}


