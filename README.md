# finops-guardrails

Cost guardrails for AWS, managed with Terraform. It stops cloud waste at two points:

- **Before merge.** A GitHub Actions bot ("CostGuard") plans every Terraform pull request, estimates the monthly cost change, checks the plan against cost policies written in Rego, and comments the result on the PR. Violations block the merge.
- **After deploy.** Budgets, anomaly detection, and Lambda functions that find idle and untagged resources in the account and switch off development servers outside working hours.

> Status: the PR bot, policies, OIDC roles, budget alerts and runtime guardrails are built. The weekly digest is next. See [Roadmap](#roadmap).

## What the bot checks

| Rule | Result | Why |
|---|---|---|
| Missing `Owner`, `Environment` or `CostCenter` tag | Blocks | Untagged spend cannot be attributed to anyone |
| gp2 storage on EBS, EC2 or RDS | Blocks | gp3 is cheaper and faster |
| CloudWatch log group with no retention | Blocks | Logs kept forever grow the bill forever |
| Total monthly cost above the hard cap | Blocks | Budget limit |
| Instance type or DB class outside the approved list | Needs approval | Someone should decide it is worth it |
| Multi-AZ database outside production | Needs approval | Doubles the instance cost |
| New NAT gateway | Needs approval | About $40/month before any traffic |
| Monthly cost increase above the threshold | Needs approval | Large changes deserve a second look |

"Needs approval" findings fail the check until a reviewer adds the `cost-approved` label to the PR. "Blocks" findings cannot be overridden. Thresholds and allow-lists live in [policies/data.json](policies/data.json).

## Layout

```
bootstrap/          one-time Terraform state bucket
infra/              the guardrails deployed to the account
modules/
  github-oidc/      keyless GitHub Actions roles (read-only plan, gated apply)
  budget-alerts/    monthly budget + cost anomaly detection
  notifications/    SNS topic and email subscribers for findings
  idle-reaper/      daily search for unattached volumes, unused IPs, idle instances
  tag-enforcer/     catches instances and volumes created without required tags
  offhours-scheduler/  stops opted-in instances at night, starts them in the morning
  lambda-function/  shared building block: function, role, expiring log group
lambdas/            Python source for the three guardrail functions
policies/           Rego policies and their unit tests
scripts/            costguard.py: evaluates policies, renders the PR comment
examples/           plan-only stacks used to demo and regression-test the bot
tests/              Python unit tests and the end-to-end check
.github/workflows/  costguard.yml (reusable), pr.yml, apply.yml
docs/adr/           design decisions
```

## Try it locally

No AWS account is needed. The example stacks use mock credentials and are never applied.

```bash
opa test policies -v
```

```bash
python -m pytest -q tests
```

```bash
bash tests/e2e.sh
```

To see the report for the wasteful stack:

```bash
cd examples/wasteful-stack && terraform init && terraform plan -out=tfplan && terraform show -json tfplan > plan.json && python ../../scripts/costguard.py --plan plan.json --policies ../../policies --target examples/wasteful-stack
```

## What the runtime guardrails do

| Guardrail | Trigger | Finds | Action |
|---|---|---|---|
| Idle reaper | Daily | Unattached volumes, unassociated Elastic IPs, instances whose CPU never passes 5% in 72 hours | Tags the resource `finops:idle-since`, emails a report with an estimated monthly waste, stops an instance still idle after 3 days |
| Tag enforcer | The moment an instance starts running, plus a daily sweep | Instances and unattached volumes missing `Owner`, `Environment` or `CostCenter` | Tags the resource `finops:untagged-since`, emails a report, stops an instance still untagged after 24 hours |
| Off-hours scheduler | 20:00 and 08:00 on weekdays (Asia/Kolkata) | Instances tagged `Schedule = office-hours` | Stops them in the evening, starts the ones it stopped in the morning |

Safety rules common to all three:

- They never delete or terminate anything. Their IAM roles do not allow it.
- They run in dry-run mode by default: findings are reported, nothing is stopped. Set `guardrails_dry_run = false` to enforce.
- A resource tagged `finops:exempt = true` is ignored.

## Use it in another repository

```yaml
jobs:
  costguard:
    uses: Arush5024/finops-guardrails/.github/workflows/costguard.yml@main
    with:
      working_directory: infra
      aws_role_arn: ${{ vars.AWS_PLAN_ROLE_ARN }}
    secrets:
      INFRACOST_API_KEY: ${{ secrets.INFRACOST_API_KEY }}
```

## Deploy to an AWS account

1. Create the state bucket (once, with admin credentials):
   `cd bootstrap && terraform init && terraform apply -var owner=<you>`
2. Copy `infra/backend.hcl.example` to `backend.hcl` and `infra/terraform.tfvars.example` to `terraform.tfvars`, and fill them in.
3. Apply `infra/` once locally to create the OIDC roles:
   `cd infra && terraform init -backend-config=backend.hcl && terraform apply`
4. In the GitHub repository settings, add:
   - Variables: `AWS_PLAN_ROLE_ARN`, `AWS_APPLY_ROLE_ARN`, `TF_STATE_BUCKET`
   - Secrets: `INFRACOST_API_KEY`, and `INFRA_TFVARS` holding the contents of your `infra/terraform.tfvars`
   - Environment: `production`, with yourself as a required reviewer

From then on, pull requests are planned with the read-only role and merges to `main` are applied through the `production` environment.

## Running cost

Designed to cost well under $1 a month in ap-south-1 without relying on the free tier. See [docs/cost.md](docs/cost.md).

## Roadmap

- [x] State bucket, OIDC roles, budget and anomaly alerts
- [x] PR bot: cost diff, Rego policies, label override, sticky comment
- [x] Idle resource reaper (Lambda)
- [x] Tag enforcer for resources created outside Terraform
- [x] Off-hours scheduler
- [ ] Weekly savings digest
