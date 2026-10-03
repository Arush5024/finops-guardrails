# The guardrails deployed into the AWS account. Applied by GitHub Actions on
# merge to main; planned (read-only) on every pull request.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # bucket and region come from backend.hcl (see backend.hcl.example)
  backend "s3" {
    key          = "infra/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "finops-guardrails"
      Owner       = var.owner
      Environment = "shared"
      CostCenter  = "platform"
      ManagedBy   = "terraform"
    }
  }
}

module "github_oidc" {
  source = "../modules/github-oidc"

  github_repo     = var.github_repo
  github_owner_id = var.github_owner_id
  github_repo_id  = var.github_repo_id
  state_bucket    = var.state_bucket

  # The apply role creates IAM roles for the guardrail Lambdas, so it needs
  # IAM write access. It is only assumable from the protected "production"
  # GitHub environment. See docs/adr/0002-github-oidc.md.
  apply_policy_arns = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}

module "budget_alerts" {
  source = "../modules/budget-alerts"

  alert_emails              = var.alert_emails
  monthly_limit_usd         = var.monthly_budget_usd
  actual_thresholds_percent = var.budget_alert_thresholds_percent

  existing_anomaly_monitor_arn = var.anomaly_monitor_arn
}

# --- Runtime guardrails: watch what actually exists in the account ---

module "notifications" {
  source = "../modules/notifications"

  emails = var.alert_emails
}

module "idle_reaper" {
  source = "../modules/idle-reaper"

  topic_arn = module.notifications.topic_arn
  dry_run   = var.guardrails_dry_run
}

module "tag_enforcer" {
  source = "../modules/tag-enforcer"

  topic_arn = module.notifications.topic_arn
  dry_run   = var.guardrails_dry_run
}

module "offhours_scheduler" {
  source = "../modules/offhours-scheduler"

  dry_run = var.guardrails_dry_run
}
