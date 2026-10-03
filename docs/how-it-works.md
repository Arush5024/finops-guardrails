# How finops-guardrails works

A plain-language guide to what this project is, why it exists, and how each part works.

## 1. The problem

Cloud bills go wrong in a predictable way. Someone writes a few lines of code that create a server, a database or a network gateway. The code is reviewed for whether it works, not for what it costs. It gets merged, the resources start running, and nobody notices the price until the bill arrives weeks later.

Three things make this hard to catch:

- **Cost is invisible in code.** `instance_type = "m5.2xlarge"` looks harmless. It costs about $318 a month.
- **Nobody knows who owns what.** Without labels (tags) on resources, a bill just says "EC2: $900". You can't tell which team or project caused it.
- **Forgotten things keep charging.** A disk that is no longer attached to anything, or a test server left on over the weekend, bills every hour until someone finds it.

The name for the practice of managing this is **FinOps** (financial operations for the cloud).

## 2. What this project does

It adds two layers of protection.

| Layer | When it acts | What it does |
|---|---|---|
| **1. The PR bot ("CostGuard")** | Before a change is accepted | Prices the change, checks it against rules, and blocks it if it is wasteful |
| **2. Account guardrails** | After things are running | Alerts on spending, and (planned) finds idle and unlabelled resources |

Layer 1 prevents problems. Layer 2 catches whatever slips past, including things people create by hand in the AWS console.

## 3. Words you need

| Term | Meaning |
|---|---|
| **Terraform** | A tool where you describe cloud resources in text files, and it creates them for you. The files are the single source of truth. |
| **Plan** | Terraform's preview: "if you accept this change, I will create these 9 things." Nothing is created at this stage. |
| **Apply** | Terraform actually making the changes in AWS. |
| **State** | Terraform's record of what it has already created, stored as a file. |
| **Pull request (PR)** | A proposed change to the code. Others review it, automated checks run on it, and then it is merged (accepted) or not. |
| **GitHub Actions** | GitHub's built-in automation. It runs scripts on GitHub's computers when something happens, such as a PR being opened. |
| **Check** | One automated test on a PR. Green means passed, red means failed. |
| **Policy** | A rule written as code, for example "every resource must have an Owner tag". |
| **OPA / Rego** | OPA is the engine that evaluates policies. Rego is the language the policies are written in. |
| **Infracost** | A service that looks up what AWS resources cost. |
| **Tag** | A label on an AWS resource, such as `Owner = arush`. |
| **OIDC** | A way for GitHub to prove its identity to AWS and get temporary access, with no stored password. |

## 4. Layer 1: the PR bot, step by step

Here is what happens when someone opens a pull request that changes Terraform code.

```
  Developer opens a pull request
              |
              v
  1. GitHub Actions starts the CostGuard workflow
              |
              v
  2. terraform plan      ->  "this change creates a database, a server, a disk..."
              |
              v
  3. Infracost           ->  "that costs $868.18 a month"
              |
              v
  4. OPA checks policies ->  "14 rules broken, 5 things need approval"
              |
              v
  5. costguard.py writes a report and posts it as a comment on the PR
              |
              v
  6. The check goes red (blocked) or green (allowed)
```

**Step 2, the plan.** The bot does not read the code directly. It asks Terraform what the code would actually do. This matters because code can hide things: an instance size might be tucked away in a variable or a shared module. The plan shows the final, real values, so nothing can be hidden from the rules.

**Step 3, the price.** The plan is sent to Infracost, which returns the monthly cost before the change, after the change, and the difference, broken down by resource.

**Step 4, the rules.** OPA evaluates every rule in the `policies/` folder against the plan and the cost. Each rule produces one of two kinds of finding:

| Kind | Meaning | Examples | Can it be overridden? |
|---|---|---|---|
| **Violation** | A mistake. There is no good reason for it. | Missing tags, old gp2 disks, logs kept forever, total above the $100 cap | No |
| **Needs approval** | A decision. It might be justified, but a person must say so. | A large server, a NAT gateway, an increase above $20 a month | Yes, by adding the `cost-approved` label to the PR |

This split is deliberate. If every rule blocked outright, people would switch the bot off the first time they had a real need for a bigger server. If every rule only warned, people would ignore it. So mistakes are blocked, and decisions are recorded: the label shows who approved the cost and when.

**Step 5, the comment.** A Python script, `scripts/costguard.py`, combines the cost and the findings into one readable comment. If the PR is updated, the same comment is edited rather than a new one added.

**Step 6, the verdict.** The script exits with "fail" if there is any violation, or any needs-approval finding without the label. GitHub shows that as a red check.

### The rules it enforces

| Rule | Kind | Why it exists |
|---|---|---|
| Every resource has `Owner`, `Environment`, `CostCenter` tags | Violation | So every dollar on the bill can be traced to someone |
| No gp2 storage | Violation | gp3 is the newer type: cheaper and faster |
| Log groups must have an expiry | Violation | Logs kept forever cost more every month, forever |
| Total cost under $100 a month | Violation | A hard ceiling |
| Server and database sizes from an approved list | Needs approval | Big machines should be a conscious choice |
| No Multi-AZ database outside production | Needs approval | It doubles the database cost; test systems rarely need it |
| No new NAT gateway | Needs approval | About $40 a month even with zero traffic |
| Cost increase under $20 a month | Needs approval | Large jumps deserve a second look |

All the numbers and lists are in `policies/data.json`, so changing a limit is a one-line edit.

### The two demo stacks

`examples/wasteful-stack` breaks nearly every rule on purpose. `examples/compliant-stack` is the same workload built properly. They exist to demonstrate the bot and to test it automatically: on every PR, a test confirms the bot still blocks the first and passes the second.

Both use fake credentials and are only ever planned, never applied. That is why the demo costs nothing and needs no AWS account.

## 5. Layer 2: account guardrails

These live in a real AWS account and are created by Terraform from the `infra/` folder.

**Built now**

| Piece | What it does |
|---|---|
| **State bucket** | An S3 bucket holding Terraform's state file, encrypted and versioned, so your laptop and GitHub share one record |
| **Keyless GitHub roles** | Let GitHub Actions work in AWS without stored keys (see section 6) |
| **Budget alerts** | Email when spending passes set percentages of a monthly budget |
| **Anomaly detection** | Email when a service suddenly costs more than its usual pattern |
| **Idle resource reaper** | Runs daily. Finds unattached disks, unused IP addresses and servers doing nothing. It labels them and emails a report; a server still idle after 3 days is stopped. It never deletes. |
| **Tag enforcer** | Runs the moment a server starts, and daily. Catches servers and disks created by hand without the required tags, labels them and emails a report; a server still untagged after 24 hours is stopped. |
| **Off-hours scheduler** | Stops servers tagged `Schedule = office-hours` at 20:00 on weekdays and starts them again at 08:00. |

All three start in "dry run" mode: they report what they find but stop nothing until enforcement is switched on. A resource tagged `finops:exempt = true` is ignored.

**The weekly digest** is a fourth function that only reads. It emails one summary: what was spent in the last 7 days compared with the 7 before, how much of the monthly budget is used, and everything the other functions still have flagged, with an estimate of the monthly waste. It can run every Monday, or be left off and triggered by hand, since each run makes one small paid query to AWS Cost Explorer.

## 6. How GitHub gets into AWS without a password

The common shortcut is to create an AWS access key and paste it into GitHub. That key never expires, and if it leaks, an attacker has your account.

This project uses **OIDC** instead:

1. When a workflow runs, GitHub issues it a short-lived signed token saying "I am a workflow in the repo `Arush5024/finops-guardrails`, running for a pull request".
2. The workflow shows that token to AWS.
3. AWS checks the signature and the repo name against a trust rule. If they match, it hands back temporary credentials that expire within an hour.

There are two roles, with different trust:

| Role | Who can use it | What it can do |
|---|---|---|
| **Plan role** | Any pull request in this repo | Read only. It can look at AWS but change nothing. |
| **Apply role** | Only the protected `production` environment, after merge | Make changes |

The reason for two: code in a pull request has not been reviewed yet. It must never be able to change real infrastructure, so it only ever gets the read-only role.

## 7. What is in each folder

| Folder | Contents |
|---|---|
| `bootstrap/` | Terraform that creates the state bucket. Run once. |
| `infra/` | Terraform for the real account: roles, budget, and later the functions |
| `modules/` | Reusable building blocks that `infra/` assembles |
| `policies/` | The rules in Rego, their settings, and their tests |
| `scripts/` | `costguard.py`, the bot's logic |
| `examples/` | The wasteful and compliant demo stacks |
| `tests/` | Tests for the script and the end-to-end check |
| `.github/workflows/` | The automation: `costguard.yml` (the bot), `pr.yml` (runs on every PR), `apply.yml` (deploys after merge) |
| `docs/` | This guide, the cost breakdown, and the design decisions |

## 8. How it is tested

| Test | What it proves |
|---|---|
| 28 policy tests | Each rule fires when it should and stays quiet when it should |
| 6 script tests | The verdict logic and the comment formatting are right |
| 27 function tests | Each guardrail function behaves correctly against a simulated AWS: what it flags, what it ignores, and that it stops nothing in dry-run mode |
| End-to-end test | Real Terraform plans of both demo stacks give the expected verdicts |
| Format, validate, lint | The Terraform code is well formed |

All of these run automatically on every pull request.

## 9. Questions an interviewer might ask

**Why not just use AWS Budgets?**
Budgets is reactive: it tells you a total after the money is spent. This blocks the spend before it happens and names the exact resource and line of code responsible. Budgets is still used here, as the backup alarm.

**Why check the plan instead of the code?**
The plan has the real, final values. Rules on source code can be bypassed by hiding a value in a variable or module.

**Why OIDC instead of access keys?**
There is no long-lived secret to leak. Credentials last an hour and are tied to this specific repo.

**Why two roles?**
Unreviewed pull request code only gets read access. Write access requires the code to be merged and the protected environment to approve.

**Why does the reaper stop resources instead of deleting them?**
Stopping can be undone. Deleting cannot. An automated tool that deletes the wrong thing destroys trust in the whole system.

**Why not AWS Config for tag enforcement?**
Config charges per rule evaluation. An event rule plus a small function does the same job for almost nothing.

**What would you improve?**
Narrow the apply role with a permissions boundary instead of full admin; restrict who can add the `cost-approved` label; make the security scanner blocking rather than report-only.

## 10. What it costs to run

Well under $1 a month, with no reliance on the AWS free tier. The breakdown is in [cost.md](cost.md).
