variable "topic_arn" {
  description = "SNS topic that findings are published to."
  type        = string
}

variable "dry_run" {
  description = "When true, idle instances are reported but never stopped."
  type        = bool
  default     = true
}

variable "schedule_expression" {
  description = "When the reaper runs. Default: daily at 03:30 UTC (09:00 IST)."
  type        = string
  default     = "cron(30 3 * * ? *)"
}

variable "min_age_hours" {
  description = "Unattached volumes younger than this are ignored."
  type        = number
  default     = 24
}

variable "cpu_threshold_percent" {
  description = "An instance whose hourly CPU never reaches this is considered idle."
  type        = number
  default     = 5
}

variable "lookback_hours" {
  description = "Window of CPU history examined. Instances younger than this are ignored."
  type        = number
  default     = 72
}

variable "grace_days" {
  description = "Days an instance may stay marked idle before it is stopped."
  type        = number
  default     = 3
}

variable "volume_usd_per_gb_month" {
  description = "Approximate EBS list prices per GB-month, used only to size the estimate in the report."
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
