# DynamoDB tables for LLM Tracer

resource "aws_dynamodb_table" "traces" {
  name         = local.traces_table_name
  billing_mode = "PAY_PER_REQUEST" # On-Demand pricing
  hash_key     = "trace_id"

  attribute {
    name = "trace_id"
    type = "S"
  }

  attribute {
    name = "project_id"
    type = "S"
  }

  attribute {
    name = "start_time"
    type = "S"
  }

  # GSI for querying traces by project
  global_secondary_index {
    name            = "project-time-index"
    hash_key        = "project_id"
    range_key       = "start_time"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup after 90 days
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery (Optional, adds cost)
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  tags = {
    Name        = local.traces_table_name
    Environment = var.environment
  }
}

resource "aws_dynamodb_table" "spans" {
  name         = local.spans_table_name
  billing_mode = "PAY_PER_REQUEST" # On-Demand pricing
  hash_key     = "span_id"

  attribute {
    name = "span_id"
    type = "S"
  }

  attribute {
    name = "trace_id"
    type = "S"
  }

  # GSI for querying spans by trace
  global_secondary_index {
    name            = "trace-index"
    hash_key        = "trace_id"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup after 90 days
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery (Optional, adds cost)
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  tags = {
    Name        = local.spans_table_name
    Environment = var.environment
  }
}
