# Shared helpers for policies evaluated against `terraform show -json` output.
#
# Two rule sets are exported from this package:
#   deny - hard violations, always block the pull request
#   warn - cost decisions that need a human: blocked until the PR carries
#          the cost-approved label
package terraform

# Resources this plan creates or updates.
changes contains rc if {
	some rc in input.resource_changes
	rc.mode == "managed"
	some action in rc.change.actions
	action in {"create", "update"}
}

# Resources this plan creates.
creates contains rc if {
	some rc in changes
	"create" in rc.change.actions
}

# Environment tag of a resource, lower-cased; "" when absent or unknown.
environment(rc) := lower(env) if {
	env := rc.change.after.tags_all.Environment
} else := ""

is_production(rc) if environment(rc) in data.finops.production_environments
