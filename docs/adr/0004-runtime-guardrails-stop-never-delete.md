# 4. Runtime guardrails stop, never delete, and start in dry run

## Context

The reaper and tag enforcer act on real resources without a human in the loop. An automated tool that removes the wrong thing once is switched off for good.

## Decision

- The functions can stop instances. They cannot terminate instances, delete volumes or release addresses: their IAM policies do not grant those actions.
- Every finding is first marked with a tag (`finops:idle-since`, `finops:untagged-since`) and reported. Action follows only after a grace period.
- Dry run is the default. Enforcement is a deliberate setting.
- `finops:exempt = true` opts a resource out.
- The off-hours scheduler only starts instances it stopped itself, and its IAM policy only allows stop and start on instances carrying the schedule tag.

## Why

- Stopping is reversible; a stopped instance keeps its disk and can be started again. Deleting is not.
- Putting the limit in IAM rather than in code means a bug cannot exceed it.
- The marker tag is the state. No database is needed to remember when a resource was first seen, and anyone looking at the resource in the console can see why it was flagged.

## Consequences

- Unattached volumes and unused addresses keep costing money until a person removes them. The report tells them to; the tool will not.
- A stopped instance still pays for its storage.

# Tag enforcement without CloudTrail or AWS Config

The enforcer is triggered by EC2's native "instance state-change" event rather than by CloudTrail API events or AWS Config rules. The native event is free and needs no trail. The cost is coverage: only EC2 instances are caught at creation time, with unattached volumes picked up by the daily sweep. Other services (RDS, S3) are covered at pull request time by the policies, but not at runtime.
