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

variable "state_bucket" {
  description = "Terraform state bucket created by bootstrap/."
  type        = string
}

variable "alert_emails" {
  description = "Email addresses that receive cost alerts."
  type        = list(string)
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the account, in USD."
  type        = number
  default     = 10
}
