# Cloudwatch monitoring and alarms

# Cost alarm (budget alert)
resource "aws_budgets_budget" "monthly_cost" {
  count = var.enable_cost_alerts ? 1 : 0

  name              = "${var.project_name}-${var.environment}-monthly-budget"
  budget_type       = "COST"
  limit_amount      = var.monthly_budget_limit
  limit_unit        = "USD"
  time_period_start = "2025-12-01_00:00"
  time_unit         = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 60
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_email_addresses
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_email_addresses
  }
}

# Lambda error alarm
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.enable_error_alerts ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda function error rate is too high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = var.sns_topic_arn != null ? [var.sns_topic_arn] : []
}

# DynamoDB read throttle alarm
resource "aws_cloudwatch_metric_alarm" "dynamodb_read_throttles" {
  count = var.enable_dynamodb_alerts ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-dynamodb-read-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReadThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "DynamoDB read capacity throttled"

  dimensions = {
    TableName = var.traces_table_name
  }

  alarm_actions = var.sns_topic_arn != null ? [var.sns_topic_arn] : []
}
