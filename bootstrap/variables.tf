variable "region" {
  description = "AWS region for the state bucket."
  type        = string
  default     = "ap-south-1"
}

variable "owner" {
  description = "Value for the Owner tag."
  type        = string
}
