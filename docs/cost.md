# Running cost

Estimates for ap-south-1 (Mumbai) at on-demand prices, assuming **no free tier**. Check the AWS pricing pages before relying on them; prices change.

## Built so far

| Component | How it is billed | Estimate per month |
|---|---|---:|
| S3 state bucket | A few KB of state plus a handful of requests | under $0.01 |
| IAM roles and OIDC provider | Free | $0 |
| AWS Budgets (alerts only, no actions) | Free | $0 |
| Cost Anomaly Detection | Free | $0 |
| Alert emails | Sent by Budgets and Cost Explorer directly, no SNS topic | $0 |
| GitHub Actions | Free for public repositories | $0 |
| Infracost | Free tier of the hosted pricing API | $0 |
| Example stacks | Plan-only with mock credentials, never applied | $0 |

## Runtime guardrails

| Component | How it is billed | Estimate per month |
|---|---|---:|
| Lambda (reaper, tag enforcer, scheduler, digest) | About 100 short invocations | under $0.01 |
| EventBridge rules and schedules | AWS service events are free; schedules are about $1 per million | under $0.01 |
| DynamoDB findings table (on-demand) | A few hundred small writes and reads | under $0.01 |
| CloudWatch Logs (14-day retention) | A few MB ingested | under $0.05 |
| CloudWatch metric reads by the reaper | $0.01 per 1,000 metrics requested | under $0.01 |
| Cost Explorer API (weekly digest) | $0.01 per request, 4 to 5 requests | about $0.05 |
| SNS email notifications | $2 per 100,000 emails | under $0.01 |

**Expected total: $0.10 to $0.30 a month, and under $1 in any case.**

## One-off testing cost

Testing the reaper needs real idle resources for a short time: a `t4g.nano` instance, a 1 GB gp3 volume and an unattached Elastic IP for about an hour is under $0.05. Destroy them straight after.

## What is deliberately avoided

| Avoided | Cost | Used instead |
|---|---|---|
| NAT gateway | about $40/month | Lambdas run outside a VPC |
| AWS Config rules | per configuration item and per evaluation | EventBridge + Lambda for tag enforcement |
| CloudTrail trail | S3 storage, plus a second trail is billed per event | EC2's native state-change events |
| DynamoDB lock table | small, but another resource | S3 native state locking |
| Applying the demo stack | $868/month (Infracost estimate) if left running | Plan-only fixtures |
| Slack forwarder Lambda | negligible, but more moving parts | Email alerts |
