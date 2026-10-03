package cost_test

import data.cost

test_small_increase_allowed if {
	i := {"diffTotalMonthlyCost": "5.50", "totalMonthlyCost": "12.00"}
	count(cost.warn) == 0 with input as i
	count(cost.deny) == 0 with input as i
}

test_large_increase_warned if {
	i := {"diffTotalMonthlyCost": "45.10", "totalMonthlyCost": "60.00"}
	cost.warn == {"This change adds $45.10/month, above the $20/month review threshold"} with input as i
	count(cost.deny) == 0 with input as i
}

test_total_above_cap_denied if {
	i := {"diffTotalMonthlyCost": "1.00", "totalMonthlyCost": "250.00"}
	cost.deny == {"Total cost would be $250.00/month, above the $100/month hard cap"} with input as i
}

test_cost_decrease_allowed if {
	i := {"diffTotalMonthlyCost": "-30.00", "totalMonthlyCost": "10.00"}
	count(cost.warn) == 0 with input as i
}

test_missing_costs_treated_as_zero if {
	count(cost.warn) == 0 with input as {}
	count(cost.deny) == 0 with input as {}
}
