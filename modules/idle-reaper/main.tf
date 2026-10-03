# Scheduled function that finds unattached volumes, unassociated Elastic IPs
# and idle instances. See lambdas/idle_reaper/handler.py.

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
  name = "${var.name_prefix}-idle-reaper"
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid = "Discover"
    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeInstances",
      "cloudwatch:GetMetricStatistics",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "MarkFindings"
    actions   = ["ec2:CreateTags"]
    resources = ["arn:aws:ec2:*:*:volume/*", "arn:aws:ec2:*:*:elastic-ip/*", "arn:aws:ec2:*:*:instance/*"]
  }

  # Stop only. The function has no permission to terminate or delete anything.
  statement {
    sid       = "StopIdleInstances"
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
  description     = "Finds idle EC2 resources, marks them and reports them"
  source_dir      = "${path.module}/../../lambdas/idle_reaper"
  policy_json     = data.aws_iam_policy_document.permissions.json
  timeout_seconds = 120

  environment = {
    DRY_RUN                 = tostring(var.dry_run)
    TOPIC_ARN               = var.topic_arn
    MIN_AGE_HOURS           = tostring(var.min_age_hours)
    CPU_THRESHOLD_PERCENT   = tostring(var.cpu_threshold_percent)
    LOOKBACK_HOURS          = tostring(var.lookback_hours)
    GRACE_DAYS              = tostring(var.grace_days)
    VOLUME_USD_PER_GB_MONTH = jsonencode(var.volume_usd_per_gb_month)
    EIP_USD_PER_HOUR        = tostring(var.eip_usd_per_hour)
  }
}

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = local.name
  description         = "Runs the idle reaper"
  schedule_expression = var.schedule_expression
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
