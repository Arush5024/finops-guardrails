output "budget_name" {
  description = "Name of the monthly budget."
  value       = aws_budgets_budget.monthly.name
}

output "anomaly_monitor_arn" {
  description = "ARN of the cost anomaly monitor."
  value       = aws_ce_anomaly_monitor.services.arn
}
