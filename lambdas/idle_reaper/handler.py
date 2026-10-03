"""Idle resource reaper.

Runs on a schedule and looks for resources that cost money while doing nothing:

  - EBS volumes attached to nothing
  - Elastic IPs associated with nothing
  - running EC2 instances with negligible CPU use

Each finding is marked with a `finops:idle-since` tag and reported by email.
An instance that is still idle after the grace period is stopped. Nothing is
ever deleted, and stopping only happens when DRY_RUN is "false".

A resource tagged `finops:exempt = true` is ignored.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import boto3

EXEMPT_TAG = "finops:exempt"
IDLE_SINCE_TAG = "finops:idle-since"
STOPPED_BY_TAG = "finops:stopped-by"

HOURS_PER_MONTH = 730


def config() -> dict:
    return {
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
        "topic_arn": os.environ.get("TOPIC_ARN", ""),
        "min_age_hours": float(os.environ.get("MIN_AGE_HOURS", "24")),
        "cpu_threshold": float(os.environ.get("CPU_THRESHOLD_PERCENT", "5")),
        "lookback_hours": int(os.environ.get("LOOKBACK_HOURS", "72")),
        "grace_days": float(os.environ.get("GRACE_DAYS", "3")),
        # Approximate list prices, used only to size the estimate in the report.
        "volume_usd_per_gb_month": json.loads(os.environ.get("VOLUME_USD_PER_GB_MONTH", "{}")),
        "eip_usd_per_hour": float(os.environ.get("EIP_USD_PER_HOUR", "0.005")),
    }


def tags_of(resource: dict) -> dict:
    return {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])}


def is_exempt(tags: dict) -> bool:
    return tags.get(EXEMPT_TAG, "").lower() == "true"


def find_unattached_volumes(ec2, now: datetime, cfg: dict) -> list[dict]:
    findings = []
    pages = ec2.get_paginator("describe_volumes").paginate(Filters=[{"Name": "status", "Values": ["available"]}])
    for page in pages:
        for volume in page["Volumes"]:
            tags = tags_of(volume)
            age_hours = (now - volume["CreateTime"]).total_seconds() / 3600
            if is_exempt(tags) or age_hours < cfg["min_age_hours"]:
                continue
            price = cfg["volume_usd_per_gb_month"].get(volume["VolumeType"])
            findings.append({
                "kind": "unattached-volume",
                "id": volume["VolumeId"],
                "detail": f"{volume['Size']} GB {volume['VolumeType']}, unattached",
                "monthly_usd": round(volume["Size"] * price, 2) if price is not None else None,
                "tags": tags,
            })
    return findings


def find_unassociated_addresses(ec2, cfg: dict) -> list[dict]:
    findings = []
    for address in ec2.describe_addresses()["Addresses"]:
        tags = tags_of(address)
        if "AssociationId" in address or is_exempt(tags):
            continue
        findings.append({
            "kind": "unassociated-address",
            "id": address["AllocationId"],
            "detail": f"Elastic IP {address['PublicIp']}, not associated",
            "monthly_usd": round(cfg["eip_usd_per_hour"] * HOURS_PER_MONTH, 2),
            "tags": tags,
        })
    return findings


def hourly_cpu(cloudwatch, instance_id: str, start: datetime, end: datetime) -> list[float]:
    """Hourly average CPU utilisation for an instance over a window."""
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=3600,
        Statistics=["Average"],
    )
    return [point["Average"] for point in response["Datapoints"]]


def find_idle_instances(ec2, cloudwatch, now: datetime, cfg: dict) -> list[dict]:
    findings = []
    window = timedelta(hours=cfg["lookback_hours"])
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                tags = tags_of(instance)
                # An instance younger than the window has not had time to prove itself idle.
                if is_exempt(tags) or now - instance["LaunchTime"] < window:
                    continue
                series = hourly_cpu(cloudwatch, instance["InstanceId"], now - window, now)
                if not series or max(series) >= cfg["cpu_threshold"]:
                    continue
                findings.append({
                    "kind": "idle-instance",
                    "id": instance["InstanceId"],
                    "detail": (
                        f"{instance['InstanceType']}, CPU peaked at {max(series):.1f}% "
                        f"over the last {cfg['lookback_hours']} hours"
                    ),
                    "monthly_usd": None,
                    "tags": tags,
                })
    return findings


def act(ec2, findings: list[dict], now: datetime, cfg: dict) -> None:
    """Mark new findings and stop instances that outlasted the grace period."""
    for finding in findings:
        idle_since = finding["tags"].get(IDLE_SINCE_TAG)

        if idle_since is None:
            ec2.create_tags(Resources=[finding["id"]], Tags=[{"Key": IDLE_SINCE_TAG, "Value": now.strftime("%Y-%m-%d")}])
            finding["action"] = "marked as idle"
            continue

        finding["action"] = f"idle since {idle_since}"
        if finding["kind"] != "idle-instance":
            continue

        try:
            marked = datetime.strptime(idle_since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - marked < timedelta(days=cfg["grace_days"]):
            continue

        if cfg["dry_run"]:
            finding["action"] = f"idle since {idle_since}; would be stopped (dry run)"
        else:
            ec2.stop_instances(InstanceIds=[finding["id"]])
            ec2.create_tags(Resources=[finding["id"]], Tags=[{"Key": STOPPED_BY_TAG, "Value": "idle-reaper"}])
            finding["action"] = f"idle since {idle_since}; stopped"


def render(findings: list[dict], cfg: dict) -> str:
    known = [f["monthly_usd"] for f in findings if f["monthly_usd"] is not None]
    lines = [
        f"The idle reaper found {len(findings)} resource(s) that cost money while doing nothing.",
        f"Estimated waste: about ${sum(known):.2f} a month (approximate list prices; idle instances not priced).",
        f"Mode: {'dry run - nothing is stopped' if cfg['dry_run'] else 'enforcing - idle instances are stopped after the grace period'}.",
        "",
    ]
    for finding in findings:
        cost = f"~${finding['monthly_usd']:.2f}/month" if finding["monthly_usd"] is not None else "cost not estimated"
        owner = finding["tags"].get("Owner", "no Owner tag")
        lines.append(f"- {finding['id']}: {finding['detail']} ({cost}; owner: {owner}) -> {finding['action']}")
    lines += ["", f"Tag a resource {EXEMPT_TAG} = true to have the reaper ignore it."]
    return "\n".join(lines)


def handler(event, context):
    cfg = config()
    ec2 = boto3.client("ec2")
    cloudwatch = boto3.client("cloudwatch")
    now = datetime.now(timezone.utc)

    findings = (
        find_unattached_volumes(ec2, now, cfg)
        + find_unassociated_addresses(ec2, cfg)
        + find_idle_instances(ec2, cloudwatch, now, cfg)
    )
    act(ec2, findings, now, cfg)

    if findings and cfg["topic_arn"]:
        boto3.client("sns").publish(
            TopicArn=cfg["topic_arn"],
            Subject=f"FinOps: {len(findings)} idle resource(s) found",
            Message=render(findings, cfg),
        )

    summary = [{key: f[key] for key in ("kind", "id", "action", "monthly_usd")} for f in findings]
    print(json.dumps({"findings": summary, "dry_run": cfg["dry_run"]}))
    return {"findings": summary}
