"""Tests for the weekly digest Lambda, run against moto's in-memory AWS."""

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REGION = "ap-south-1"
HANDLER = Path(__file__).resolve().parents[1] / "lambdas" / "weekly_digest" / "handler.py"

spec = importlib.util.spec_from_file_location("weekly_digest_handler", HANDLER)
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)

TODAY = date(2026, 10, 19)
CFG = {"topic_arn": "", "monthly_budget_usd": 10.0, "volume_usd_per_gb_month": {"gp3": 0.1}, "eip_usd_per_hour": 0.005}


@pytest.fixture
def ec2(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("TOPIC_ARN", raising=False)
    with mock_aws():
        yield boto3.client("ec2", region_name=REGION)


def tag(ec2, resource_id: str, key: str, value: str) -> None:
    ec2.create_tags(Resources=[resource_id], Tags=[{"Key": key, "Value": value}])


# --- spend ---


def test_spend_splits_weeks_and_month():
    costs = {
        date(2026, 9, 30): {"Amazon S3": 9.00},  # last month: counted nowhere
        date(2026, 10, 1): {"Amazon S3": 1.00},  # this month only
        date(2026, 10, 5): {"Amazon S3": 2.00},  # previous 7 days (Oct 5-11)
        date(2026, 10, 11): {"AWS Lambda": 0.50},  # previous 7 days
        date(2026, 10, 12): {"Amazon EC2": 3.00, "Amazon S3": 0.25},  # last 7 days (Oct 12-18)
        date(2026, 10, 18): {"Amazon EC2": 1.00, "AWS Lambda": 0.001},  # last 7 days
    }

    spend = digest.summarise_spend(costs, TODAY)

    assert spend["last_7_days"] == pytest.approx(4.251)
    assert spend["previous_7_days"] == pytest.approx(2.50)
    assert spend["month_to_date"] == pytest.approx(7.751)
    # Sorted by cost; services under half a cent are left out.
    assert spend["top_services"] == [("Amazon EC2", 4.00), ("Amazon S3", 0.25)]


def test_spend_with_no_data_is_zero():
    spend = digest.summarise_spend({}, TODAY)

    assert spend == {"last_7_days": 0, "previous_7_days": 0, "month_to_date": 0, "top_services": []}


# --- findings ---


def test_findings_come_from_marker_tags_with_age_and_cost(ec2):
    volume_id = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=50, VolumeType="gp3")["VolumeId"]
    allocation_id = ec2.allocate_address(Domain="vpc")["AllocationId"]
    instance_id = ec2.run_instances(ImageId="ami-12345678", InstanceType="t3.micro", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    tag(ec2, volume_id, digest.IDLE_SINCE_TAG, "2026-10-09")
    tag(ec2, allocation_id, digest.IDLE_SINCE_TAG, "2026-10-17")
    tag(ec2, instance_id, digest.UNTAGGED_SINCE_TAG, "2026-10-18T12:37Z")
    tag(ec2, instance_id, digest.STOPPED_BY_TAG, "tag-enforcer")

    findings, stopped = digest.collect_findings(ec2, TODAY, CFG)

    assert findings == [
        {"id": volume_id, "type": "volume", "reason": "idle", "days": 10, "monthly_usd": 5.0},
        {"id": allocation_id, "type": "elastic-ip", "reason": "idle", "days": 2, "monthly_usd": 3.65},
        {"id": instance_id, "type": "instance", "reason": "untagged", "days": 1, "monthly_usd": None},
    ]
    assert stopped == [instance_id]


def test_no_markers_means_no_findings(ec2):
    ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=1, VolumeType="gp3")

    assert digest.collect_findings(ec2, TODAY, CFG) == ([], [])


def test_unparseable_marker_date_is_reported_without_age(ec2):
    volume_id = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=1, VolumeType="gp3")["VolumeId"]
    tag(ec2, volume_id, digest.UNTAGGED_SINCE_TAG, "yesterday")

    findings, _ = digest.collect_findings(ec2, TODAY, CFG)

    assert findings[0]["days"] is None
    assert "unknown age" in digest.render(None, findings, [], TODAY, CFG)


# --- report ---


def test_report_shows_spend_findings_and_waste():
    spend = {"last_7_days": 4.25, "previous_7_days": 2.50, "month_to_date": 7.75, "top_services": [("Amazon EC2", 4.00)]}
    findings = [
        {"id": "vol-1", "type": "volume", "reason": "idle", "days": 10, "monthly_usd": 5.0},
        {"id": "i-1", "type": "instance", "reason": "untagged", "days": 1, "monthly_usd": None},
    ]

    report = digest.render(spend, findings, ["i-1"], TODAY, CFG)

    assert "week ending 2026-10-18" in report
    assert "$4.25  (previous 7 days: $2.50, +70%)" in report
    assert "$7.75 of $10.00 budget (78%)" in report
    assert "volume vol-1: idle for 10 day(s), ~$5.00/month" in report
    assert "instance i-1: untagged for 1 day(s)" in report
    assert "about $5.00 a month" in report
    assert "STOPPED BY GUARDRAILS (1)" in report


def test_report_for_a_quiet_week():
    spend = {"last_7_days": 0.0, "previous_7_days": 0.0, "month_to_date": 0.0, "top_services": []}

    report = digest.render(spend, [], [], TODAY, CFG)

    assert "no earlier spend to compare" in report
    assert "Nothing is currently flagged" in report
    assert "No instances are currently stopped" in report


# --- handler ---


def test_handler_still_reports_when_cost_explorer_fails(ec2, monkeypatch):
    def unavailable(today):
        raise RuntimeError("Cost Explorer is not enabled")

    monkeypatch.setattr(digest, "fetch_daily_costs", unavailable)
    allocation_id = ec2.allocate_address(Domain="vpc")["AllocationId"]
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    tag(ec2, allocation_id, digest.IDLE_SINCE_TAG, yesterday)

    result = digest.handler({}, None)

    assert "Cost data is not available" in result["message"]
    assert [f["id"] for f in result["findings"]] == [allocation_id]


def test_handler_publishes_one_email(ec2, monkeypatch):
    sns = boto3.client("sns", region_name=REGION)
    monkeypatch.setenv("TOPIC_ARN", sns.create_topic(Name="alerts")["TopicArn"])
    monkeypatch.setattr(digest, "fetch_daily_costs", lambda today: {today - timedelta(days=1): {"Amazon S3": 1.5}})
    sent = []
    real_client = digest.boto3.client

    class Recorder:
        def publish(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(digest.boto3, "client", lambda service, *a, **k: Recorder() if service == "sns" else real_client(service, *a, **k))

    digest.handler({}, None)

    assert len(sent) == 1
    assert sent[0]["Subject"] == "FinOps weekly digest: $1.50 last week, 0 open finding(s)"
