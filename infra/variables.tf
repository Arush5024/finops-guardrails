variable "region" {
  description = "AWS region for the guardrails."
  type        = string
  default     = "ap-south-1"
}

variable "owner" {
  description = "Value for the Owner tag."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository that runs the pipelines, as owner/name."
  type        = string
}

variable "github_owner_id" {
  description = "Numeric ID of the repository owner, for immutable OIDC subject claims."
  type        = string
  default     = null
}

variable "github_repo_id" {
  description = "Numeric ID of the repository, for immutable OIDC subject claims."
  type        = string
  default     = null
}

variable "state_bucket" {
  description = "Terraform state bucket created by bootstrap/."
  type        = string
}

variable "alert_emails" {
  description = "Email addresses that receive cost alerts."
  type        = list(string)
  sensitive   = true
}

variable "budget_alert_thresholds_percent" {
  description = "Percentages of the monthly budget at which an alert is sent. At most four: a budget allows five alerts and one is used for the forecast."
  type        = list(number)
  default     = [20, 50, 80, 100]

  validation {
    condition     = length(var.budget_alert_thresholds_percent) <= 4
    error_message = "At most four thresholds are allowed."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the account, in USD."
  type        = number
  default     = 10
}

variable "anomaly_monitor_arn" {
  description = "ARN of the account's existing per-service cost anomaly monitor. Leave null to create one."
  type        = string
  default     = null
}

variable "guardrails_dry_run" {
  description = "When true, the runtime guardrails report findings but never stop anything."
  type        = bool
  default     = true
}

variable "weekly_digest_enabled" {
  description = "Send the digest automatically every Monday. When false, it is only sent when the function is invoked by hand."
  type        = bool
  default     = false
}
