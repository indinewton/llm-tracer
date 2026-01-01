output "budget_name" {
  description = "Budget name"
  value       = var.enable_cost_alerts ? aws_budgets_budget.monthly_cost[0].name : null
}