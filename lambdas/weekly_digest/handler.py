"""Weekly digest.

Sends one summary email:

  - spend for the last 7 days against the 7 days before, and month to date
    against the budget
  - every resource the other guardrails currently have flagged, how long it
    has been flagged, and the estimated monthly waste
  - instances the guardrails have stopped

Findings are read from the marker tags the other functions leave on resources
(`finops:idle-since`, `finops:untagged-since`, `finops:stopped-by`), so there
is no separate store of findings to keep in step.

Cost Explorer bills per request, so all spend figures come from one query.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import boto3

IDLE_SINCE_TAG = "finops:idle-since"
UNTAGGED_SINCE_TAG = "finops:untagged-since"
STOPPED_BY_TAG = "finops:stopped-by"

HOURS_PER_MONTH = 730
TOP_SERVICES = 5

# The resource kind is read from the id: it is unambiguous, unlike the
# ResourceType that DescribeTags reports for addresses.
KIND_BY_PREFIX = {"vol-": "volume", "eipalloc-": "elastic-ip", "i-": "instance"}


def config() -> dict:
    return {
        "topic_arn": os.environ.get("TOPIC_ARN", ""),
        "monthly_budget_usd": float(os.environ.get("MONTHLY_BUDGET_USD", "0")),
        "volume_usd_per_gb_month": json.loads(os.environ.get("VOLUME_USD_PER_GB_MONTH", "{}")),
        "eip_usd_per_hour": float(os.environ.get("EIP_USD_PER_HOUR", "0.005")),
    }


def fetch_daily_costs(today: date) -> dict[date, dict[str, float]]:
    """Cost per day per service, from the earlier of 14 days ago and the start of the month."""
    start = min(today - timedelta(days=14), today.replace(day=1))
    # Cost Explorer is a global service served from us-east-1.
    ce = boto3.client("ce", region_name="us-east-1")
    request = {
        "TimePeriod": {"Start": start.isoformat(), "End": today.isoformat()},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
    }

    costs: dict[date, dict[str, float]] = {}
    while True:
        response = ce.get_cost_and_usage(**request)
        for day in response["ResultsByTime"]:
            when = date.fromisoformat(day["TimePeriod"]["Start"])
            costs[when] = {
                group["Keys"][0]: float(group["Metrics"]["UnblendedCost"]["Amount"]) for group in day["Groups"]
            }
        if not response.get("NextPageToken"):
            return costs
        request["NextPageToken"] = response["NextPageToken"]


def summarise_spend(costs: dict[date, dict[str, float]], today: date) -> dict:
    def total(first: date, last: date) -> float:
        return sum(sum(services.values()) for day, services in costs.items() if first <= day <= last)

    week_start = today - timedelta(days=7)
    by_service: dict[str, float] = defaultdict(float)
    for day, services in costs.items():
        if week_start <= day < today:
            for service, amount in services.items():
                by_service[service] += amount

    top = sorted(by_service.items(), key=lambda item: item[1], reverse=True)
    return {
        "last_7_days": total(week_start, today - timedelta(days=1)),
        "previous_7_days": total(today - timedelta(days=14), week_start - timedelta(days=1)),
        "month_to_date": total(today.replace(day=1), today - timedelta(days=1)),
        "top_services": [(service, amount) for service, amount in top[:TOP_SERVICES] if amount >= 0.005],
    }


def days_since(value: str, today: date) -> int | None:
    """Age in days of a marker tag value such as 2026-10-03 or 2026-10-03T12:37Z."""
    try:
        return (today - date.fromisoformat(value[:10])).days
    except ValueError:
        return None


def kind_of(tag: dict) -> str:
    for prefix, kind in KIND_BY_PREFIX.items():
        if tag["ResourceId"].startswith(prefix):
            return kind
    return tag["ResourceType"]


def existing(ec2, markers: list[dict]) -> set[str]:
    """Ids among the marked resources that still exist.

    DescribeTags keeps returning the tags of a deleted volume or terminated
    instance for a while, so a marker alone does not prove the resource is
    still there.
    """
    ids: dict[str, list[str]] = defaultdict(list)
    for resource_id in {tag["ResourceId"] for tag in markers}:
        for prefix, kind in KIND_BY_PREFIX.items():
            if resource_id.startswith(prefix):
                ids[kind].append(resource_id)

    found: set[str] = set()
    if ids["volume"]:
        volumes = ec2.describe_volumes(Filters=[{"Name": "volume-id", "Values": ids["volume"]}])["Volumes"]
        found |= {volume["VolumeId"] for volume in volumes}
    if ids["elastic-ip"]:
        addresses = ec2.describe_addresses(Filters=[{"Name": "allocation-id", "Values": ids["elastic-ip"]}])["Addresses"]
        found |= {address["AllocationId"] for address in addresses}
    if ids["instance"]:
        reservations = ec2.describe_instances(Filters=[
            {"Name": "instance-id", "Values": ids["instance"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ])["Reservations"]
        found |= {instance["InstanceId"] for reservation in reservations for instance in reservation["Instances"]}
    return found


def collect_findings(ec2, today: date, cfg: dict) -> tuple[list[dict], list[str]]:
    """Returns (open findings, ids of instances stopped by the guardrails)."""
    pages = ec2.get_paginator("describe_tags").paginate(
        Filters=[{"Name": "key", "Values": [IDLE_SINCE_TAG, UNTAGGED_SINCE_TAG, STOPPED_BY_TAG]}]
    )
    markers = [tag for page in pages for tag in page["Tags"]]
    alive = existing(ec2, markers)
    markers = [tag for tag in markers if tag["ResourceId"] in alive]

    stopped = sorted(tag["ResourceId"] for tag in markers if tag["Key"] == STOPPED_BY_TAG)
    flagged = [tag for tag in markers if tag["Key"] != STOPPED_BY_TAG]

    # Only idle volumes and addresses have a price we can estimate.
    idle_volume_ids = [t["ResourceId"] for t in flagged if t["Key"] == IDLE_SINCE_TAG and kind_of(t) == "volume"]
    volumes = {}
    if idle_volume_ids:
        described = ec2.describe_volumes(VolumeIds=idle_volume_ids)["Volumes"]
        volumes = {volume["VolumeId"]: volume for volume in described}

    findings = []
    for tag in flagged:
        monthly_usd = None
        if tag["Key"] == IDLE_SINCE_TAG and kind_of(tag) == "elastic-ip":
            monthly_usd = round(cfg["eip_usd_per_hour"] * HOURS_PER_MONTH, 2)
        elif tag["ResourceId"] in volumes:
            volume = volumes[tag["ResourceId"]]
            price = cfg["volume_usd_per_gb_month"].get(volume["VolumeType"])
            monthly_usd = round(volume["Size"] * price, 2) if price is not None else None

        findings.append({
            "id": tag["ResourceId"],
            "type": kind_of(tag),
            "reason": "idle" if tag["Key"] == IDLE_SINCE_TAG else "untagged",
            "days": days_since(tag["Value"], today),
            "monthly_usd": monthly_usd,
        })

    findings.sort(key=lambda f: (-(f["days"] or 0), f["id"], f["reason"]))
    return findings, stopped


def usd(amount: float) -> str:
    return f"${amount:,.2f}"


def render(spend: dict | None, findings: list[dict], stopped: list[str], today: date, cfg: dict) -> str:
    lines = [f"FinOps weekly digest for the week ending {today - timedelta(days=1)}", ""]

    lines.append("SPEND")
    if spend is None:
        lines.append("  Cost data is not available (Cost Explorer can take 24 hours to activate on a new account).")
    else:
        previous = spend["previous_7_days"]
        if previous >= 0.01:
            change = f"{(spend['last_7_days'] - previous) / previous:+.0%}"
        else:
            change = "no earlier spend to compare"
        lines.append(f"  Last 7 days:     {usd(spend['last_7_days'])}  (previous 7 days: {usd(previous)}, {change})")
        if cfg["monthly_budget_usd"] > 0:
            share = spend["month_to_date"] / cfg["monthly_budget_usd"]
            budget = usd(cfg["monthly_budget_usd"])
            lines.append(f"  Month to date:   {usd(spend['month_to_date'])} of {budget} budget ({share:.0%})")
        else:
            lines.append(f"  Month to date:   {usd(spend['month_to_date'])}")
        for service, amount in spend["top_services"]:
            lines.append(f"    {usd(amount):>9}  {service}")
    lines.append("")

    lines.append(f"OPEN FINDINGS ({len(findings)})")
    if not findings:
        lines.append("  Nothing is currently flagged as idle or untagged.")
    for finding in findings:
        age = f"{finding['days']} day(s)" if finding["days"] is not None else "unknown age"
        cost = f", ~{usd(finding['monthly_usd'])}/month" if finding["monthly_usd"] is not None else ""
        lines.append(f"  - {finding['type']} {finding['id']}: {finding['reason']} for {age}{cost}")
    waste = sum(f["monthly_usd"] for f in findings if f["monthly_usd"] is not None)
    if waste:
        lines.append(f"  Estimated waste if left in place: about {usd(waste)} a month (approximate list prices).")
    lines.append("")

    lines.append(f"STOPPED BY GUARDRAILS ({len(stopped)})")
    lines.append("  " + (", ".join(stopped) if stopped else "No instances are currently stopped by the guardrails."))
    return "\n".join(lines)


def handler(event, context):
    cfg = config()
    today = datetime.now(timezone.utc).date()

    try:
        spend = summarise_spend(fetch_daily_costs(today), today)
    except Exception as error:  # noqa: BLE001 - the digest is still useful without cost data
        print(json.dumps({"cost_explorer_error": str(error)}))
        spend = None

    findings, stopped = collect_findings(boto3.client("ec2"), today, cfg)
    message = render(spend, findings, stopped, today, cfg)

    if cfg["topic_arn"]:
        last_week = usd(spend["last_7_days"]) if spend else "cost unavailable"
        boto3.client("sns").publish(
            TopicArn=cfg["topic_arn"],
            Subject=f"FinOps weekly digest: {last_week} last week, {len(findings)} open finding(s)",
            Message=message,
        )

    print(json.dumps({"findings": len(findings), "stopped": len(stopped), "cost_available": spend is not None}))
    return {"findings": findings, "stopped": stopped, "message": message}
