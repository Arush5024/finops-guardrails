#!/usr/bin/env bash
# End-to-end regression test: plans both example stacks with real Terraform
# and checks that CostGuard blocks the wasteful one and passes the compliant
# one. Needs terraform, opa and python on PATH; needs no AWS account.
set -euo pipefail

TERRAFORM=${TERRAFORM_BIN:-terraform}
PYTHON=${PYTHON_BIN:-python3}
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

check() {
  local stack=$1 want=$2 got=0

  "$TERRAFORM" -chdir="$root/examples/$stack" init -backend=false -input=false >/dev/null
  "$TERRAFORM" -chdir="$root/examples/$stack" plan -input=false -out="$work/$stack.tfplan" >/dev/null
  "$TERRAFORM" -chdir="$root/examples/$stack" show -json "$work/$stack.tfplan" >"$work/$stack.json"

  "$PYTHON" "$root/scripts/costguard.py" --plan "$work/$stack.json" --policies "$root/policies" \
    --target "examples/$stack" --out "$work/$stack.md" || got=$?

  if [ "$got" -ne "$want" ]; then
    echo "FAIL: $stack exited $got, expected $want"
    cat "$work/$stack.md"
    exit 1
  fi
  echo "ok: $stack exited $got"
}

check wasteful-stack 1
check compliant-stack 0

# Every wasteful resource the policies know about must be reported.
for expected in \
  'aws_instance.app` is missing required tags' \
  'aws_ebs_volume.scratch` uses gp2' \
  'aws_cloudwatch_log_group.app` never expires logs' \
  'aws_nat_gateway.main` adds a NAT gateway' \
  'instance type m5.2xlarge'; do
  if ! grep -qF "$expected" "$work/wasteful-stack.md"; then
    echo "FAIL: wasteful-stack report is missing: $expected"
    exit 1
  fi
done
echo "ok: wasteful-stack report lists the expected findings"
