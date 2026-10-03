variable "dry_run" {
  description = "When true, the function logs what it would do and changes nothing."
  type        = bool
  default     = true
}

variable "schedule_tag_key" {
  description = "Tag key an instance uses to opt in."
  type        = string
  default     = "Schedule"
}

variable "schedule_tag_value" {
  description = "Tag value an instance uses to opt in."
  type        = string
  default     = "office-hours"
}

variable "timezone" {
  description = "Time zone the schedule expressions are evaluated in."
  type        = string
  default     = "Asia/Kolkata"
}

variable "stop_schedule_expression" {
  description = "When scheduled instances are stopped. Default: 20:00 on weekdays."
  type        = string
  default     = "cron(0 20 ? * MON-FRI *)"
}

variable "start_schedule_expression" {
  description = "When scheduled instances are started. Default: 08:00 on weekdays."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "finops-guardrails"
}
