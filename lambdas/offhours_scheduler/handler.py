"""Off-hours scheduler.

Stops instances that opt in with a schedule tag (by default
`Schedule = office-hours`) in the evening and starts them again in the
morning. Invoked by EventBridge Scheduler with {"action": "stop"} or
{"action": "start"}.

Only instances this function stopped are started again, so an instance
someone stopped by hand stays stopped. Nothing happens when DRY_RUN is "true".
"""

from __future__ import annotations

import json
import os

import boto3

STOPPED_BY_TAG = "finops:stopped-by"
STOPPED_BY_VALUE = "offhours-scheduler"


def config() -> dict:
    return {
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
        "tag_key": os.environ.get("SCHEDULE_TAG_KEY", "Schedule"),
        "tag_value": os.environ.get("SCHEDULE_TAG_VALUE", "office-hours"),
    }


def find_instances(ec2, filters: list[dict]) -> list[str]:
    pages = ec2.get_paginator("describe_instances").paginate(Filters=filters)
    return [instance["InstanceId"] for page in pages for reservation in page["Reservations"] for instance in reservation["Instances"]]


def handler(event, context):
    cfg = config()
    action = (event or {}).get("action")
    if action not in ("stop", "start"):
        raise ValueError(f"action must be 'stop' or 'start', got {action!r}")

    ec2 = boto3.client("ec2")
    scheduled = {"Name": f"tag:{cfg['tag_key']}", "Values": [cfg["tag_value"]]}

    if action == "stop":
        instance_ids = find_instances(ec2, [scheduled, {"Name": "instance-state-name", "Values": ["running"]}])
        if instance_ids and not cfg["dry_run"]:
            ec2.stop_instances(InstanceIds=instance_ids)
            ec2.create_tags(Resources=instance_ids, Tags=[{"Key": STOPPED_BY_TAG, "Value": STOPPED_BY_VALUE}])
    else:
        instance_ids = find_instances(ec2, [
            scheduled,
            {"Name": "instance-state-name", "Values": ["stopped"]},
            {"Name": f"tag:{STOPPED_BY_TAG}", "Values": [STOPPED_BY_VALUE]},
        ])
        if instance_ids and not cfg["dry_run"]:
            ec2.start_instances(InstanceIds=instance_ids)
            ec2.delete_tags(Resources=instance_ids, Tags=[{"Key": STOPPED_BY_TAG}])

    result = {"action": action, "instances": instance_ids, "dry_run": cfg["dry_run"]}
    print(json.dumps(result))
    return result
