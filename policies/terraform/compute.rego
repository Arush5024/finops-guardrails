package terraform

# Sizes outside the allow-list are not forbidden, but someone has to decide
# they are worth the money.

warn contains msg if {
	some rc in changes
	rc.type in {"aws_instance", "aws_launch_template"}
	instance_type := rc.change.after.instance_type
	not instance_type in data.finops.allowed_instance_types
	msg := sprintf("`%s` uses instance type %s, which is outside the approved list", [rc.address, instance_type])
}

warn contains msg if {
	some rc in changes
	rc.type == "aws_db_instance"
	instance_class := rc.change.after.instance_class
	not instance_class in data.finops.allowed_db_instance_classes
	msg := sprintf("`%s` uses instance class %s, which is outside the approved list", [rc.address, instance_class])
}

# Multi-AZ doubles the instance cost; outside production it rarely pays off.
warn contains msg if {
	some rc in changes
	rc.type == "aws_db_instance"
	rc.change.after.multi_az == true
	not is_production(rc)
	msg := sprintf("`%s` enables Multi-AZ outside production, doubling its instance cost", [rc.address])
}
