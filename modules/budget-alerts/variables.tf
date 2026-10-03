variable "alert_emails" {
  description = "Email addresses that receive budget and anomaly alerts."
  type        = list(string)

  validation {
    condition     = length(var.alert_emails) > 0
    error_message = "At least one alert email is required."
  }
}

variable "monthly_limit_usd" {
  description = "Monthly cost budget for the account, in USD."
  type        = number
}

variable "actual_thresholds_percent" {
  description = "Percentages of the budget at which an actual-spend alert is sent."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "anomaly_threshold_usd" {
  description = "Minimum total impact, in USD, for a cost anomaly to be reported."
  type        = number
  default     = 1
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "finops-guardrails"
}

variable "existing_anomaly_monitor_arn" {
  description = "ARN of an existing per-service cost anomaly monitor to reuse. When null, a monitor is created."
  type        = string
  default     = null
}
