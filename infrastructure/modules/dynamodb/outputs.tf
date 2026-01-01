output "traces_table_name" {
  description = "Name of the traces DynamoDB table"
  value       = aws_dynamodb_table.traces.name
}

output "traces_table_arn" {
  description = "ARN of the traces DynamoDB table"
  value       = aws_dynamodb_table.traces.arn
}

output "spans_table_name" {
  description = "Name of the spans DynamoDB table"
  value       = aws_dynamodb_table.spans.name
}

output "spans_table_arn" {
  description = "ARN of the spans DynamoDB table"
  value       = aws_dynamodb_table.spans.arn
}
