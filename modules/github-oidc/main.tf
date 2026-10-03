# Lets GitHub Actions assume AWS roles with short-lived OIDC tokens, so the
# repository never stores AWS access keys.
#
# Two roles:
#   plan  - read-only, assumable from pull requests and main
#   apply - write access, assumable only from the protected GitHub environment

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
  oidc_url          = "token.actions.githubusercontent.com"
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.existing_oidc_provider_arn

  # GitHub's token names the repository in its "sub" claim. Newer repositories
  # get the immutable form, owner@owner_id/name@repo_id, which stops a
  # re-registered owner or repository name from inheriting this trust.
  owner      = split("/", var.github_repo)[0]
  repo       = split("/", var.github_repo)[1]
  immutable  = var.github_owner_id != null && var.github_repo_id != null
  repository = local.immutable ? "${local.owner}@${var.github_owner_id}/${local.repo}@${var.github_repo_id}" : var.github_repo
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://${local.oidc_url}"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_url}:sub"
      values = [
        "repo:${local.repository}:pull_request",
        "repo:${local.repository}:ref:refs/heads/main",
      ]
    }
  }
}

data "aws_iam_policy_document" "apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:sub"
      values   = ["repo:${local.repository}:environment:${var.apply_environment}"]
    }
  }
}

resource "aws_iam_role" "plan" {
  name                 = "${var.name_prefix}-gha-plan"
  description          = "Read-only role for terraform plan in GitHub Actions"
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# terraform plan takes a state lock, which with use_lockfile is an S3 object.
data "aws_iam_policy_document" "plan_state_lock" {
  statement {
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/*.tflock"]
  }
}

resource "aws_iam_role_policy" "plan_state_lock" {
  name   = "state-lock"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_state_lock.json
}

resource "aws_iam_role" "apply" {
  name                 = "${var.name_prefix}-gha-apply"
  description          = "Role for terraform apply from the protected GitHub environment"
  assume_role_policy   = data.aws_iam_policy_document.apply_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "apply" {
  for_each = toset(var.apply_policy_arns)

  role       = aws_iam_role.apply.name
  policy_arn = each.value
}
