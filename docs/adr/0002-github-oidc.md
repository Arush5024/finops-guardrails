# 2. GitHub OIDC with separate plan and apply roles

## Context

GitHub Actions needs AWS access to plan and apply. The usual shortcut is an IAM user's access key stored as a repository secret.

## Decision

No AWS keys are stored in GitHub. Workflows exchange a GitHub OIDC token for short-lived credentials on one of two roles:

- **plan**: `ReadOnlyAccess` plus write access to state lock objects only. Trusted for pull requests and `main`.
- **apply**: trusted only for jobs running in the `production` GitHub environment, which can require a human approval.

## Why

- A leaked long-lived key is the most common way AWS accounts are compromised. OIDC credentials expire within the hour and cannot be exfiltrated from repository settings.
- Pull request code is untrusted until reviewed. It only ever gets a read-only role, so a malicious PR cannot change infrastructure.
- Tying the apply role to an environment, not a branch, lets GitHub enforce required reviewers before any write.

## Subject claim format

AWS matches the token's `sub` claim exactly. Newer GitHub repositories issue it in an immutable form, `repo:owner@owner_id/name@repo_id:...`, so that a re-registered owner or repository name cannot inherit the trust. The module builds that form when `github_owner_id` and `github_repo_id` are set. The first pipeline run against AWS failed on this; the actual claim was read from the failed `AssumeRoleWithWebIdentity` event in CloudTrail.

## Consequences

- The first apply of `infra/` must be run locally, because the roles do not exist yet.
- The apply role currently has `AdministratorAccess`, since it creates IAM roles for the guardrail Lambdas. Narrowing it with a permissions boundary is a known follow-up.
- `ReadOnlyAccess` can read S3 objects, including Terraform state. Nothing secret is kept in state in this project.
