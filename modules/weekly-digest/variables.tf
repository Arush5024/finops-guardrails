variable "topic_arn" {
  description = "SNS topic the digest is published to."
  type        = string
}

variable "schedule_enabled" {
  description = "Whether the digest is sent automatically on the schedule. When false, it is only sent when the function is invoked by hand."
  type        = bool
  default     = false
}

variable "schedule_expression" {
  description = "When the digest is sent. Default: Mondays at 03:30 UTC (09:00 IST)."
  type        = string
  default     = "cron(30 3 ? * MON *)"
}

variable "monthly_budget_usd" {
  description = "Monthly budget that month-to-date spend is compared against. 0 hides the comparison."
  type        = number
  default     = 0
}

variable "volume_usd_per_gb_month" {
  description = "Approximate EBS list prices per GB-month, used only to size the waste estimate."
  type        = map(number)
  default = {
    gp3      = 0.0912
    gp2      = 0.114
    st1      = 0.054
    sc1      = 0.0174
    standard = 0.08
  }
}

variable "eip_usd_per_hour" {
  description = "Approximate hourly price of an idle public IPv4 address."
  type        = number
  default     = 0.005
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "finops-guardrails"
}
