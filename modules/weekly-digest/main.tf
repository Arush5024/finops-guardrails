# Function that emails a weekly summary of spend and open findings.
# See lambdas/weekly_digest/handler.py.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

locals {
  name = "${var.name_prefix}-weekly-digest"
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "ReadSpend"
    actions   = ["ce:GetCostAndUsage"]
    resources = ["*"]
  }

  # Read only: the digest reports on findings, it never changes a resource.
  statement {
    sid       = "ReadFindings"
    actions   = ["ec2:DescribeTags", "ec2:DescribeVolumes", "ec2:DescribeAddresses", "ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "Notify"
    actions   = ["sns:Publish"]
    resources = [var.topic_arn]
  }
}

module "function" {
  source = "../lambda-function"

  name        = local.name
  description = "Emails a weekly summary of spend and open cost findings"
  source_dir  = "${path.module}/../../lambdas/weekly_digest"
  policy_json = data.aws_iam_policy_document.permissions.json

  environment = {
    TOPIC_ARN               = var.topic_arn
    MONTHLY_BUDGET_USD      = tostring(var.monthly_budget_usd)
    VOLUME_USD_PER_GB_MONTH = jsonencode(var.volume_usd_per_gb_month)
    EIP_USD_PER_HOUR        = tostring(var.eip_usd_per_hour)
  }
}

# Each run makes one billable Cost Explorer request, so the schedule can be
# left disabled and the function invoked by hand when a digest is wanted.
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = local.name
  description         = "Sends the weekly FinOps digest"
  schedule_expression = var.schedule_expression
  state               = var.schedule_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "schedule" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = module.function.arn
}

resource "aws_lambda_permission" "schedule" {
  statement_id  = "AllowSchedule"
  action        = "lambda:InvokeFunction"
  function_name = module.function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
