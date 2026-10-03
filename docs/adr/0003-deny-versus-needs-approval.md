# 3. Two severities: block, and needs approval

## Context

A cost policy that only ever blocks gets disabled the first time someone has a legitimate reason to spend money. A policy that only warns gets ignored.

## Decision

Rules are split into two sets:

- `deny`: never justified (gp2, missing tags, logs kept forever, total above the hard cap). Always fails the check.
- `warn`: sometimes justified (a large instance, a NAT gateway, a big cost increase). Fails the check until the PR carries the `cost-approved` label.

## Why

- The split separates mistakes from decisions. Mistakes are fixed; decisions are made by a person and recorded.
- A label is visible in the PR timeline with who added it and when, which gives an audit trail for free.
- The workflow reruns on `labeled` and `unlabeled`, so approving does not need a new commit.

## Consequences

- Anyone with triage permission can add the label. Restricting it to specific approvers would need a CODEOWNERS-style check and is not implemented.
- The label approves all `warn` findings on the PR at once, not individual ones.
