variable "emails" {
  description = "Email addresses subscribed to guardrail findings."
  type        = list(string)
  sensitive   = true
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "finops-guardrails"
}
