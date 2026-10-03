variable "github_repo" {
  description = "GitHub repository allowed to assume the roles, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repo))
    error_message = "github_repo must be in owner/name form."
  }
}

variable "state_bucket" {
  description = "Terraform state bucket the plan role needs lock access to."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for the IAM role names."
  type        = string
  default     = "finops-guardrails"
}

variable "apply_environment" {
  description = "GitHub environment that is allowed to assume the apply role."
  type        = string
  default     = "production"
}

variable "apply_policy_arns" {
  description = "Managed policy ARNs attached to the apply role."
  type        = list(string)
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set to false if the account already has one."
  type        = bool
  default     = true
}

variable "existing_oidc_provider_arn" {
  description = "ARN of an existing GitHub OIDC provider, used when create_oidc_provider is false."
  type        = string
  default     = null
}
