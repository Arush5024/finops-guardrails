"""Tests for the guardrail Lambdas, run against moto's in-memory AWS."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

LAMBDAS = Path(__file__).resolve().parents[1] / "lambdas"
REGION = "ap-south-1"
GOOD_TAGS = {"Owner": "arush", "Environment": "dev", "CostCenter": "demo"}


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_handler", LAMBDAS / name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reaper = load("idle_reaper")
enforcer = load("tag_enforcer")
scheduler = load("offhours_scheduler")


@pytest.fixture
def aws(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    for key in ("DRY_RUN", "TOPIC_ARN", "MIN_AGE_HOURS", "GRACE_DAYS", "GRACE_HOURS", "LOOKBACK_HOURS"):
        monkeypatch.delenv(key, raising=False)
    with mock_aws():
        yield boto3.client("ec2", region_name=REGION)


def as_tags(tags: dict) -> list[dict]:
    return [{"Key": key, "Value": value} for key, value in tags.items()]


def launch(ec2, tags: dict | None = None) -> str:
    args = {"ImageId": "ami-12345678", "InstanceType": "t3.micro", "MinCount": 1, "MaxCount": 1}
    if tags:
        args["TagSpecifications"] = [{"ResourceType": "instance", "Tags": as_tags(tags)}]
    return ec2.run_instances(**args)["Instances"][0]["InstanceId"]


def state(ec2, instance_id: str) -> str:
    return ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]


def tags(ec2, resource_id: str) -> dict:
    found = ec2.describe_tags(Filters=[{"Name": "resource-id", "Values": [resource_id]}])["Tags"]
    return {tag["Key"]: tag["Value"] for tag in found}


def days_ago(days: float, fmt: str) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(fmt)


# --- idle reaper ---


def test_reaper_marks_unattached_volume_and_estimates_cost(aws, monkeypatch):
    monkeypatch.setenv("MIN_AGE_HOURS", "0")
    monkeypatch.setenv("VOLUME_USD_PER_GB_MONTH", '{"gp3": 0.1}')
    volume_id = aws.create_volume(AvailabilityZone=f"{REGION}a", Size=50, VolumeType="gp3")["VolumeId"]

    findings = reaper.handler({}, None)["findings"]

    assert findings == [{"kind": "unattached-volume", "id": volume_id, "action": "marked as idle", "monthly_usd": 5.0}]
    assert reaper.IDLE_SINCE_TAG in tags(aws, volume_id)
    # The volume itself is never removed.
    assert aws.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]["State"] == "available"


def test_reaper_ignores_new_exempt_and_attached_volumes(aws, monkeypatch):
    aws.create_volume(AvailabilityZone=f"{REGION}a", Size=10, VolumeType="gp3")  # younger than 24h
    monkeypatch.setenv("MIN_AGE_HOURS", "24")
    assert reaper.handler({}, None)["findings"] == []

    monkeypatch.setenv("MIN_AGE_HOURS", "0")
    aws.create_volume(
        AvailabilityZone=f"{REGION}a", Size=10, VolumeType="gp3",
        TagSpecifications=[{"ResourceType": "volume", "Tags": as_tags({reaper.EXEMPT_TAG: "true"})}],
    )
    findings = reaper.handler({}, None)["findings"]
    assert len(findings) == 1  # only the first, non-exempt volume


def test_reaper_finds_unassociated_address(aws):
    allocation_id = aws.allocate_address(Domain="vpc")["AllocationId"]

    findings = reaper.handler({}, None)["findings"]

    assert [f["id"] for f in findings] == [allocation_id]
    assert findings[0]["monthly_usd"] == 3.65


def test_reaper_stops_idle_instance_only_after_grace_and_when_enforcing(aws, monkeypatch):
    instance_id = launch(aws, GOOD_TAGS)
    monkeypatch.setenv("LOOKBACK_HOURS", "0")
    monkeypatch.setattr(reaper, "hourly_cpu", lambda *args: [0.4, 1.2])

    # First sighting: marked, not stopped.
    assert reaper.handler({}, None)["findings"][0]["action"] == "marked as idle"
    assert state(aws, instance_id) == "running"

    # Past the grace period but in dry run: reported, not stopped.
    aws.create_tags(Resources=[instance_id], Tags=as_tags({reaper.IDLE_SINCE_TAG: days_ago(5, "%Y-%m-%d")}))
    assert "would be stopped" in reaper.handler({}, None)["findings"][0]["action"]
    assert state(aws, instance_id) == "running"

    # Enforcing: stopped, never terminated.
    monkeypatch.setenv("DRY_RUN", "false")
    assert reaper.handler({}, None)["findings"][0]["action"].endswith("stopped")
    assert state(aws, instance_id) == "stopped"
    assert tags(aws, instance_id)[reaper.STOPPED_BY_TAG] == "idle-reaper"


def test_reaper_leaves_busy_instance_alone(aws, monkeypatch):
    launch(aws, GOOD_TAGS)
    monkeypatch.setenv("LOOKBACK_HOURS", "0")
    monkeypatch.setattr(reaper, "hourly_cpu", lambda *args: [0.5, 42.0])

    assert reaper.handler({}, None)["findings"] == []


def test_reaper_skips_instance_with_no_metrics(aws, monkeypatch):
    launch(aws, GOOD_TAGS)
    monkeypatch.setenv("LOOKBACK_HOURS", "0")
    monkeypatch.setattr(reaper, "hourly_cpu", lambda *args: [])

    assert reaper.handler({}, None)["findings"] == []


def test_reaper_emails_a_summary(aws, monkeypatch):
    sns = boto3.client("sns", region_name=REGION)
    topic_arn = sns.create_topic(Name="alerts")["TopicArn"]
    monkeypatch.setenv("TOPIC_ARN", topic_arn)
    aws.allocate_address(Domain="vpc")
    sent = []
    monkeypatch.setattr(reaper.boto3, "client", wrap_sns(reaper.boto3.client, sent))

    reaper.handler({}, None)

    assert len(sent) == 1
    assert "1 idle resource" in sent[0]["Subject"]
    assert "dry run" in sent[0]["Message"]


def wrap_sns(real_client, sent: list):
    """Returns a boto3.client replacement that records SNS publishes."""

    class Recorder:
        def publish(self, **kwargs):
            sent.append(kwargs)

    return lambda service, *args, **kwargs: Recorder() if service == "sns" else real_client(service, *args, **kwargs)


# --- tag enforcer ---


def test_enforcer_marks_untagged_instance_from_event(aws):
    instance_id = launch(aws, {"Owner": "arush"})
    other = launch(aws)  # also untagged, but not the subject of the event

    event = {"detail-type": "EC2 Instance State-change Notification", "detail": {"instance-id": instance_id, "state": "running"}}
    findings = enforcer.handler(event, None)["findings"]

    assert findings == [{"kind": "instance", "id": instance_id, "missing": ["Environment", "CostCenter"], "action": "marked as untagged"}]
    assert enforcer.UNTAGGED_SINCE_TAG in tags(aws, instance_id)
    assert enforcer.UNTAGGED_SINCE_TAG not in tags(aws, other)


def test_enforcer_passes_tagged_and_exempt_instances(aws):
    launch(aws, GOOD_TAGS)
    launch(aws, {enforcer.EXEMPT_TAG: "true"})

    assert enforcer.handler({}, None)["findings"] == []


def test_enforcer_clears_marker_once_tags_are_added(aws):
    instance_id = launch(aws)
    enforcer.handler({}, None)
    assert enforcer.UNTAGGED_SINCE_TAG in tags(aws, instance_id)

    aws.create_tags(Resources=[instance_id], Tags=as_tags(GOOD_TAGS))

    assert enforcer.handler({}, None)["findings"] == []
    assert enforcer.UNTAGGED_SINCE_TAG not in tags(aws, instance_id)


def test_enforcer_stops_only_after_grace_and_when_enforcing(aws, monkeypatch):
    instance_id = launch(aws)
    stale = days_ago(2, enforcer.TIME_FORMAT)
    aws.create_tags(Resources=[instance_id], Tags=as_tags({enforcer.UNTAGGED_SINCE_TAG: stale}))

    assert "would be stopped" in enforcer.handler({}, None)["findings"][0]["action"]
    assert state(aws, instance_id) == "running"

    monkeypatch.setenv("DRY_RUN", "false")
    assert enforcer.handler({}, None)["findings"][0]["action"].endswith("stopped")
    assert state(aws, instance_id) == "stopped"


def test_enforcer_does_not_stop_within_grace(aws, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    instance_id = launch(aws)

    enforcer.handler({}, None)  # marks
    enforcer.handler({}, None)  # still within the 24h grace

    assert state(aws, instance_id) == "running"


def test_enforcer_sweep_covers_unattached_volumes(aws):
    volume_id = aws.create_volume(AvailabilityZone=f"{REGION}a", Size=1, VolumeType="gp3")["VolumeId"]

    findings = enforcer.handler({}, None)["findings"]

    assert [(f["kind"], f["id"]) for f in findings] == [("volume", volume_id)]


# --- off-hours scheduler ---


def test_scheduler_stops_only_opted_in_instances(aws, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    scheduled = launch(aws, {"Schedule": "office-hours"})
    always_on = launch(aws, GOOD_TAGS)

    result = scheduler.handler({"action": "stop"}, None)

    assert result["instances"] == [scheduled]
    assert state(aws, scheduled) == "stopped"
    assert state(aws, always_on) == "running"


def test_scheduler_starts_only_what_it_stopped(aws, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    by_scheduler = launch(aws, {"Schedule": "office-hours"})
    by_hand = launch(aws, {"Schedule": "office-hours"})
    scheduler.handler({"action": "stop"}, None)
    aws.delete_tags(Resources=[by_hand], Tags=[{"Key": scheduler.STOPPED_BY_TAG}])

    result = scheduler.handler({"action": "start"}, None)

    assert result["instances"] == [by_scheduler]
    assert state(aws, by_scheduler) == "running"
    assert state(aws, by_hand) == "stopped"
    assert scheduler.STOPPED_BY_TAG not in tags(aws, by_scheduler)


def test_scheduler_dry_run_changes_nothing(aws):
    instance_id = launch(aws, {"Schedule": "office-hours"})

    result = scheduler.handler({"action": "stop"}, None)

    assert result == {"action": "stop", "instances": [instance_id], "dry_run": True}
    assert state(aws, instance_id) == "running"


def test_scheduler_rejects_unknown_action(aws):
    with pytest.raises(ValueError):
        scheduler.handler({"action": "terminate"}, None)
