package terraform

# gp3 is about 20% cheaper per GB than gp2 with better baseline performance,
# so there is no reason to create new gp2 storage.

deny contains msg if {
	some rc in changes
	rc.type == "aws_ebs_volume"
	rc.change.after.type == "gp2"
	msg := sprintf("`%s` uses gp2; use gp3 (cheaper and faster)", [rc.address])
}

deny contains msg if {
	some rc in changes
	rc.type in {"aws_instance", "aws_launch_template"}
	some block in {"root_block_device", "ebs_block_device"}
	some device in object.get(rc.change.after, block, [])
	device.volume_type == "gp2"
	msg := sprintf("`%s` has a gp2 %s; use gp3 (cheaper and faster)", [rc.address, block])
}

deny contains msg if {
	some rc in changes
	rc.type == "aws_db_instance"
	rc.change.after.storage_type == "gp2"
	msg := sprintf("`%s` uses gp2 storage; use gp3 (cheaper and faster)", [rc.address])
}

# A log group with no retention keeps every log line forever and the bill only
# ever grows.
deny contains msg if {
	some rc in changes
	rc.type == "aws_cloudwatch_log_group"
	object.get(rc.change.after, "retention_in_days", 0) in {0, null}
	msg := sprintf("`%s` never expires logs; set retention_in_days", [rc.address])
}
