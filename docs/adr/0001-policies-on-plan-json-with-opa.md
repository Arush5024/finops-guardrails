# 1. Evaluate policies on the plan JSON with OPA

## Context

Cost rules could be checked against the Terraform source (HCL) or against the plan. They could be run with Conftest, Checkov custom policies, Sentinel, or OPA directly.

## Decision

Policies are written in Rego and evaluated with `opa eval` against the output of `terraform show -json`.

## Why

- The plan contains resolved values. A rule on HCL can be bypassed by hiding an instance type in a variable or a module; a rule on the plan cannot.
- The plan knows the action (create, update, delete), so rules can apply only to what the PR changes.
- Infracost also emits JSON, so the cost threshold is a Rego rule in the same engine rather than a separate mechanism.
- OPA directly, rather than Conftest, means one binary that is identical locally and in CI, with `opa test` for unit tests. Conftest would add a second tool that wraps the same engine.

## Consequences

- A plan is needed, so the check needs provider credentials (read-only) for real stacks.
- Values unknown until apply cannot be checked. The tag rule handles the common case explicitly: the AWS provider leaves `tags_all` unknown for a resource with no tags, so the rule falls back to the resource's own `tags`. A resource that relies only on `default_tags` whose values are unknown at plan time would be reported as untagged; this is accepted as rare.
