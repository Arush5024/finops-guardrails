import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import costguard
from costguard import Findings


def test_deny_blocks_even_with_label():
    findings = Findings(deny=["bad"], warn=["pricey"])
    assert costguard.decide(findings, {"cost-approved"}) == "blocked"


def test_warn_needs_label():
    findings = Findings(warn=["pricey"])
    assert costguard.decide(findings, set()) == "needs-approval"
    assert costguard.decide(findings, {"cost-approved"}) == "approved"


def test_no_findings_passes():
    assert costguard.decide(Findings(), set()) == "passed"


def test_money_formatting():
    assert costguard.fmt_usd(1234.5) == "$1,234.50"
    assert costguard.fmt_usd(12, signed=True) == "+$12.00"
    assert costguard.fmt_usd(-12, signed=True) == "-$12.00"
    assert costguard.fmt_usd(0, signed=True) == "$0.00"
    assert costguard.money(None) == 0.0
    assert costguard.money("3.5") == 3.5


def test_report_lists_cost_and_findings():
    infracost = {
        "pastTotalMonthlyCost": "0",
        "totalMonthlyCost": "50",
        "diffTotalMonthlyCost": "50",
        "projects": [
            {
                "diff": {
                    "resources": [
                        {"name": "aws_instance.app", "monthlyCost": "40"},
                        {"name": "aws_ebs_volume.data", "monthlyCost": "10"},
                        {"name": "aws_vpc.main", "monthlyCost": None},
                    ]
                }
            }
        ],
    }
    findings = Findings(deny=["`aws_ebs_volume.data` uses gp2"], warn=["`aws_instance.app` is large"])
    report = costguard.render("infra", "blocked", findings, infracost)

    assert report.startswith(costguard.COMMENT_MARKER)
    assert "**+$50.00**" in report
    assert report.index("aws_instance.app` | +$40.00") < report.index("aws_ebs_volume.data` | +$10.00")
    assert "aws_vpc.main" not in report
    assert "### Violations (1)" in report
    assert "### Needs approval (1)" in report


def test_report_without_infracost():
    report = costguard.render("infra", "passed", Findings(), None)
    assert "Cost estimate skipped" in report
    assert "Passed" in report
