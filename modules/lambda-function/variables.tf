variable "name" {
  description = "Name of the function, its role and its log group."
  type        = string
}

variable "description" {
  description = "What the function does."
  type        = string
}

variable "source_dir" {
  description = "Directory containing handler.py."
  type        = string
}

variable "policy_json" {
  description = "IAM policy document granting the permissions the function's code needs."
  type        = string
}

variable "environment" {
  description = "Environment variables for the function."
  type        = map(string)
  default     = {}
}

variable "timeout_seconds" {
  description = "Function timeout in seconds."
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "Days to keep the function's logs."
  type        = number
  default     = 14
}
