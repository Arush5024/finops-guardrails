# Stops instances that opt in with a schedule tag outside working hours and
# starts them again in the morning. See lambdas/offhours_scheduler/handler.py.

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
  name = "${var.name_prefix}-offhours-scheduler"

  schedules = {
    stop  = var.stop_schedule_expression
    start = var.start_schedule_expression
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "Discover"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  # Only instances that opted in with the schedule tag can be stopped or started.
  statement {
    sid       = "StopAndStartScheduledInstances"
    actions   = ["ec2:StopInstances", "ec2:StartInstances"]
    resources = ["arn:aws:ec2:*:*:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/${var.schedule_tag_key}"
      values   = [var.schedule_tag_value]
    }
  }

  statement {
    sid       = "TrackWhatWasStopped"
    actions   = ["ec2:CreateTags", "ec2:DeleteTags"]
    resources = ["arn:aws:ec2:*:*:instance/*"]

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "aws:TagKeys"
      values   = ["finops:stopped-by"]
    }
  }
}

module "function" {
  source = "../lambda-function"

  name        = local.name
  description = "Stops and starts instances tagged for office hours"
  source_dir  = "${path.module}/../../lambdas/offhours_scheduler"
  policy_json = data.aws_iam_policy_document.permissions.json

  environment = {
    DRY_RUN            = tostring(var.dry_run)
    SCHEDULE_TAG_KEY   = var.schedule_tag_key
    SCHEDULE_TAG_VALUE = var.schedule_tag_value
  }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "scheduler_invoke" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [module.function.arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-invoke"
  description        = "Lets EventBridge Scheduler invoke the off-hours scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_invoke.json
}

# EventBridge Scheduler, rather than a plain rule, because it understands time
# zones: the schedule follows local working hours.
resource "aws_scheduler_schedule" "this" {
  for_each = local.schedules

  name                         = "${local.name}-${each.key}"
  schedule_expression          = each.value
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = module.function.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ action = each.key })
  }
}
