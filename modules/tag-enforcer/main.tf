# Function that catches EC2 resources created without the required tags. It
# reacts as soon as an instance starts running, and sweeps daily.
# See lambdas/tag_enforcer/handler.py.

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
  name = "${var.name_prefix}-tag-enforcer"
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "Discover"
    actions   = ["ec2:DescribeInstances", "ec2:DescribeVolumes"]
    resources = ["*"]
  }

  statement {
    sid       = "MarkFindings"
    actions   = ["ec2:CreateTags", "ec2:DeleteTags"]
    resources = ["arn:aws:ec2:*:*:instance/*", "arn:aws:ec2:*:*:volume/*"]
  }

  # Stop only. The function has no permission to terminate or delete anything.
  statement {
    sid       = "StopUntaggedInstances"
    actions   = ["ec2:StopInstances"]
    resources = ["arn:aws:ec2:*:*:instance/*"]
  }

  statement {
    sid       = "Notify"
    actions   = ["sns:Publish"]
    resources = [var.topic_arn]
  }
}

module "function" {
  source = "../lambda-function"

  name            = local.name
  description     = "Reports and stops EC2 resources missing cost-allocation tags"
  source_dir      = "${path.module}/../../lambdas/tag_enforcer"
  policy_json     = data.aws_iam_policy_document.permissions.json
  timeout_seconds = 120

  environment = {
    DRY_RUN       = tostring(var.dry_run)
    TOPIC_ARN     = var.topic_arn
    REQUIRED_TAGS = join(",", var.required_tags)
    GRACE_HOURS   = tostring(var.grace_hours)
  }
}

# EC2 emits this event natively, so no CloudTrail trail is needed.
resource "aws_cloudwatch_event_rule" "instance_running" {
  name        = "${local.name}-instance-running"
  description = "An EC2 instance entered the running state"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail      = { state = ["running"] }
  })
}

resource "aws_cloudwatch_event_rule" "sweep" {
  name                = "${local.name}-sweep"
  description         = "Daily sweep for untagged resources"
  schedule_expression = var.sweep_schedule_expression
}

locals {
  rules = {
    instance-running = aws_cloudwatch_event_rule.instance_running
    sweep            = aws_cloudwatch_event_rule.sweep
  }
}

resource "aws_cloudwatch_event_target" "this" {
  for_each = local.rules

  rule = each.value.name
  arn  = module.function.arn
}

resource "aws_lambda_permission" "this" {
  for_each = local.rules

  statement_id  = "Allow-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = module.function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}
