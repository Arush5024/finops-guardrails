# Policies evaluated against `infracost diff --format json` output.
package cost

monthly_increase := to_number(object.get(input, "diffTotalMonthlyCost", "0"))

monthly_total := to_number(object.get(input, "totalMonthlyCost", "0"))

warn contains msg if {
	limit := data.finops.cost.max_monthly_increase_usd
	monthly_increase > limit
	msg := sprintf("This change adds $%.2f/month, above the $%d/month review threshold", [monthly_increase, limit])
}

deny contains msg if {
	limit := data.finops.cost.max_total_monthly_usd
	monthly_total > limit
	msg := sprintf("Total cost would be $%.2f/month, above the $%d/month hard cap", [monthly_total, limit])
}
