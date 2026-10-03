# The SNS topic the guardrail functions publish their findings to, with email
# subscribers. Each address receives a confirmation email it must accept.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  # Indexed by position, not by address, so addresses stay out of plan output.
  count = nonsensitive(length(var.emails))

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.emails[count.index]
}
