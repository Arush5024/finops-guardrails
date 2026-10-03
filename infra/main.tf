# The guardrails deployed into the AWS account. Applied by GitHub Actions on
# merge to main; planned (read-only) on every pull request.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
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

  github_repo  = var.github_repo
  state_bucket = var.state_bucket

  # The apply role creates IAM roles for the guardrail Lambdas, so it needs
  # IAM write access. It is only assumable from the protected "production"
  # GitHub environment. See docs/adr/0002-github-oidc.md.
  apply_policy_arns = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}

module "budget_alerts" {
  source = "../modules/budget-alerts"

  alert_emails      = var.alert_emails
  monthly_limit_usd = var.monthly_budget_usd
}
