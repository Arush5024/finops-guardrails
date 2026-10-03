variable "topic_arn" {
  description = "SNS topic that findings are published to."
  type        = string
}

variable "dry_run" {
  description = "When true, untagged instances are reported but never stopped."
  type        = bool
  default     = true
}

variable "required_tags" {
  description = "Tag keys every instance and volume must carry."
  type        = list(string)
  default     = ["Owner", "Environment", "CostCenter"]
}

variable "grace_hours" {
  description = "Hours an instance may stay untagged before it is stopped."
  type        = number
  default     = 24
}

variable "sweep_schedule_expression" {
  description = "When the full sweep runs. Default: daily at 03:45 UTC (09:15 IST)."
  type        = string
  default     = "cron(45 3 * * ? *)"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "finops-guardrails"
}
