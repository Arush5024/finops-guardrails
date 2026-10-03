#!/usr/bin/env python3
"""CostGuard: evaluate a Terraform plan against cost policies and report.

Reads a Terraform plan (JSON) and, optionally, an Infracost diff (JSON),
evaluates the Rego policies with OPA, writes a Markdown report suitable for a
pull request comment, and exits non-zero if the change must not merge.

Outcomes:
    blocked         a deny rule fired; exit 1
    needs-approval  only warn rules fired and the PR lacks the approval
                    label; exit 1
    approved        warn rules fired but the approval label is present; exit 0
    passed          nothing fired; exit 0
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

APPROVAL_LABEL = "cost-approved"
COMMENT_MARKER = "<!-- costguard -->"
TOP_RESOURCES = 10


@dataclass
class Findings:
    deny: list[str] = field(default_factory=list)
    warn: list[str] = field(default_factory=list)

    def extend(self, other: "Findings") -> None:
        self.deny.extend(other.deny)
        self.warn.extend(other.warn)


def opa_eval(policies: Path, input_file: Path, package: str) -> Findings:
    """Evaluate one policy package against one input document."""
    opa = os.environ.get("OPA_BIN", "opa")
    result = subprocess.run(
        [opa, "eval", "--format", "json", "--data", str(policies), "--input", str(input_file), f"data.{package}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"opa eval failed for data.{package}: {result.stderr.strip() or result.stdout.strip()}")

    results = json.loads(result.stdout).get("result", [])
    value = results[0]["expressions"][0]["value"] if results else {}
    return Findings(deny=sorted(value.get("deny", [])), warn=sorted(value.get("warn", [])))


def decide(findings: Findings, labels: set[str]) -> str:
    if findings.deny:
        return "blocked"
    if findings.warn:
        return "approved" if APPROVAL_LABEL in labels else "needs-approval"
    return "passed"


def money(value: str | float | None) -> float:
    return float(value) if value not in (None, "") else 0.0


def fmt_usd(amount: float, signed: bool = False) -> str:
    sign = "-" if amount < 0 else ("+" if signed and amount > 0 else "")
    return f"{sign}${abs(amount):,.2f}"


def cost_section(infracost: dict | None) -> list[str]:
    if infracost is None:
        return ["### Cost", "", "_Cost estimate skipped: no Infracost API key configured._", ""]

    before = money(infracost.get("pastTotalMonthlyCost"))
    after = money(infracost.get("totalMonthlyCost"))
    diff = money(infracost.get("diffTotalMonthlyCost"))

    lines = [
        "### Cost",
        "",
        "| Monthly cost | Before | After | Change |",
        "|---|---:|---:|---:|",
        f"| **Total** | {fmt_usd(before)} | {fmt_usd(after)} | **{fmt_usd(diff, signed=True)}** |",
        "",
    ]

    changed = [
        (resource["name"], money(resource.get("monthlyCost")))
        for project in infracost.get("projects", [])
        for resource in (project.get("diff") or {}).get("resources", [])
    ]
    changed = sorted((c for c in changed if c[1] != 0), key=lambda c: abs(c[1]), reverse=True)

    if changed:
        lines += ["<details><summary>Largest changes by resource</summary>", "", "| Resource | Monthly change |", "|---|---:|"]
        lines += [f"| `{name}` | {fmt_usd(cost, signed=True)} |" for name, cost in changed[:TOP_RESOURCES]]
        if len(changed) > TOP_RESOURCES:
            lines.append(f"| _{len(changed) - TOP_RESOURCES} more_ | |")
        lines += ["", "</details>", ""]

    return lines


def render(target: str, outcome: str, findings: Findings, infracost: dict | None) -> str:
    headline = {
        "blocked": "❌ **Blocked** — fix the violations below before merging.",
        "needs-approval": f"⚠️ **Needs approval** — a reviewer must add the `{APPROVAL_LABEL}` label.",
        "approved": f"✅ **Approved** — cost findings accepted via the `{APPROVAL_LABEL}` label.",
        "passed": "✅ **Passed** — no cost policy findings.",
    }[outcome]

    lines = [COMMENT_MARKER, f"## CostGuard: `{target}`", "", headline, ""]
    lines += cost_section(infracost)

    if findings.deny:
        lines += [f"### Violations ({len(findings.deny)})", "", "These always block the merge.", ""]
        lines += [f"- {msg}" for msg in findings.deny]
        lines.append("")

    if findings.warn:
        lines += [f"### Needs approval ({len(findings.warn)})", "", f"Allowed once the PR has the `{APPROVAL_LABEL}` label.", ""]
        lines += [f"- {msg}" for msg in findings.warn]
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", required=True, type=Path, help="terraform show -json output")
    parser.add_argument("--infracost", type=Path, help="infracost diff --format json output")
    parser.add_argument("--policies", required=True, type=Path, help="directory containing the Rego policies")
    parser.add_argument("--target", default=".", help="name of the stack, shown in the report")
    parser.add_argument("--labels", default="", help="comma-separated pull request labels")
    parser.add_argument("--out", type=Path, help="write the Markdown report here (default: stdout)")
    args = parser.parse_args(argv)

    findings = opa_eval(args.policies, args.plan, "terraform")

    infracost = None
    if args.infracost and args.infracost.is_file():
        infracost = json.loads(args.infracost.read_text(encoding="utf-8"))
        findings.extend(opa_eval(args.policies, args.infracost, "cost"))

    labels = {label.strip() for label in args.labels.split(",") if label.strip()}
    outcome = decide(findings, labels)
    report = render(args.target, outcome, findings, infracost)

    if args.out:
        args.out.write_text(report, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report)

    print(f"costguard: {outcome} ({len(findings.deny)} violations, {len(findings.warn)} needing approval)", file=sys.stderr)
    return 1 if outcome in ("blocked", "needs-approval") else 0


if __name__ == "__main__":
    sys.exit(main())
