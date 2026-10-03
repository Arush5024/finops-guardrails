"""Tag enforcer.

Catches EC2 resources created outside Terraform (and so outside the pull
request checks) without the required cost-allocation tags.

Triggered two ways:

  - by EventBridge the moment an instance enters the running state
  - on a daily schedule, to sweep every instance and unattached volume

An untagged resource is marked with a `finops:untagged-since` tag and reported
by email. An instance still untagged after the grace period is stopped, but
only when DRY_RUN is "false". Nothing is deleted. Once the tags are added the
marker is removed.

A resource tagged `finops:exempt = true` is ignored.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import boto3

EXEMPT_TAG = "finops:exempt"
UNTAGGED_SINCE_TAG = "finops:untagged-since"
STOPPED_BY_TAG = "finops:stopped-by"
TIME_FORMAT = "%Y-%m-%dT%H:%MZ"


def config() -> dict:
    return {
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
        "topic_arn": os.environ.get("TOPIC_ARN", ""),
        "required_tags": [t.strip() for t in os.environ.get("REQUIRED_TAGS", "Owner,Environment,CostCenter").split(",") if t.strip()],
        "grace_hours": float(os.environ.get("GRACE_HOURS", "24")),
    }


def tags_of(resource: dict) -> dict:
    return {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])}


def missing_tags(tags: dict, required: list[str]) -> list[str]:
    return [key for key in required if not tags.get(key)]


def list_instances(ec2, instance_id: str | None) -> list[dict]:
    if instance_id:
        pages = ec2.get_paginator("describe_instances").paginate(InstanceIds=[instance_id])
    else:
        pages = ec2.get_paginator("describe_instances").paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
        )
    return [instance for page in pages for reservation in page["Reservations"] for instance in reservation["Instances"]]


def list_unattached_volumes(ec2) -> list[dict]:
    # Attached volumes belong to their instance and are covered through it.
    pages = ec2.get_paginator("describe_volumes").paginate(Filters=[{"Name": "status", "Values": ["available"]}])
    return [volume for page in pages for volume in page["Volumes"]]


def check(ec2, resource_id: str, kind: str, tags: dict, state: str | None, now: datetime, cfg: dict) -> dict | None:
    """Check one resource; returns a finding, or None if it is compliant."""
    if tags.get(EXEMPT_TAG, "").lower() == "true":
        return None

    missing = missing_tags(tags, cfg["required_tags"])
    since = tags.get(UNTAGGED_SINCE_TAG)

    if not missing:
        if since is not None:
            ec2.delete_tags(Resources=[resource_id], Tags=[{"Key": UNTAGGED_SINCE_TAG}])
        return None

    finding = {"kind": kind, "id": resource_id, "missing": missing}

    if since is None:
        ec2.create_tags(Resources=[resource_id], Tags=[{"Key": UNTAGGED_SINCE_TAG, "Value": now.strftime(TIME_FORMAT)}])
        finding["action"] = "marked as untagged"
        return finding

    finding["action"] = f"untagged since {since}"
    if kind != "instance" or state != "running":
        return finding

    try:
        marked = datetime.strptime(since, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return finding
    if now - marked < timedelta(hours=cfg["grace_hours"]):
        return finding

    if cfg["dry_run"]:
        finding["action"] = f"untagged since {since}; would be stopped (dry run)"
    else:
        ec2.stop_instances(InstanceIds=[resource_id])
        ec2.create_tags(Resources=[resource_id], Tags=[{"Key": STOPPED_BY_TAG, "Value": "tag-enforcer"}])
        finding["action"] = f"untagged since {since}; stopped"
    return finding


def render(findings: list[dict], cfg: dict) -> str:
    if cfg["dry_run"]:
        mode = "dry run - nothing is stopped"
    else:
        mode = f"enforcing - untagged instances are stopped after {cfg['grace_hours']:g} hours"

    lines = [
        f"{len(findings)} resource(s) are missing required cost-allocation tags ({', '.join(cfg['required_tags'])}).",
        f"Mode: {mode}.",
        "",
    ]
    for finding in findings:
        lines.append(f"- {finding['kind']} {finding['id']}: missing {', '.join(finding['missing'])} -> {finding['action']}")
    lines += ["", f"Add the tags to clear the finding, or tag the resource {EXEMPT_TAG} = true to have it ignored."]
    return "\n".join(lines)


def handler(event, context):
    cfg = config()
    ec2 = boto3.client("ec2")
    now = datetime.now(timezone.utc)

    # An instance state-change event names one instance; anything else is a full sweep.
    instance_id = (event or {}).get("detail", {}).get("instance-id")

    findings = []
    for instance in list_instances(ec2, instance_id):
        finding = check(ec2, instance["InstanceId"], "instance", tags_of(instance), instance["State"]["Name"], now, cfg)
        if finding:
            findings.append(finding)

    if not instance_id:
        for volume in list_unattached_volumes(ec2):
            finding = check(ec2, volume["VolumeId"], "volume", tags_of(volume), None, now, cfg)
            if finding:
                findings.append(finding)

    if findings and cfg["topic_arn"]:
        boto3.client("sns").publish(
            TopicArn=cfg["topic_arn"],
            Subject=f"FinOps: {len(findings)} untagged resource(s)",
            Message=render(findings, cfg),
        )

    print(json.dumps({"findings": findings, "dry_run": cfg["dry_run"], "trigger": "event" if instance_id else "sweep"}))
    return {"findings": findings}
