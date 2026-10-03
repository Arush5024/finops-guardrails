package terraform_test

import data.terraform

good_tags := {"Owner": "arush", "Environment": "dev", "CostCenter": "platform"}

# Builds a one-resource plan.
plan(type, actions, after) := {"resource_changes": [{
	"address": sprintf("%s.this", [type]),
	"mode": "managed",
	"type": type,
	"change": {"actions": actions, "after": after, "after_unknown": {}},
}]}

tagged(after) := object.union(after, {"tags_all": good_tags})

# --- tags ---

test_missing_tags_denied if {
	result := terraform.deny with input as plan("aws_ebs_volume", ["create"], {"type": "gp3", "tags_all": {"Owner": "arush"}})
	result == {"`aws_ebs_volume.this` is missing required tags: Environment, CostCenter"}
}

test_empty_tag_value_denied if {
	tags := object.union(good_tags, {"Owner": ""})
	result := terraform.deny with input as plan("aws_ebs_volume", ["create"], {"type": "gp3", "tags_all": tags})
	count(result) == 1
}

test_all_tags_allowed if {
	result := terraform.deny with input as plan("aws_ebs_volume", ["create"], tagged({"type": "gp3"}))
	count(result) == 0
}

test_untaggable_resource_ignored if {
	result := terraform.deny with input as plan("aws_iam_role_policy", ["create"], {"name": "x"})
	count(result) == 0
}

# Builds a one-volume plan whose tags_all is unknown at plan time.
unknown_tags_all_plan(tags, unknown_tags) := {"resource_changes": [{
	"address": "aws_ebs_volume.this",
	"mode": "managed",
	"type": "aws_ebs_volume",
	"change": {
		"actions": ["create"],
		"after": {"type": "gp3", "tags": tags},
		"after_unknown": {"tags_all": true, "tags": unknown_tags},
	},
}]}

# This is what the provider emits for a resource with no tags at all.
test_untagged_resource_denied if {
	result := terraform.deny with input as unknown_tags_all_plan(null, false)
	result == {"`aws_ebs_volume.this` is missing required tags: Owner, Environment, CostCenter"}
}

test_tag_value_known_at_apply_counts_as_present if {
	tags := {"Environment": "dev", "CostCenter": "platform"}
	result := terraform.deny with input as unknown_tags_all_plan(tags, {"Owner": true})
	count(result) == 0
}

test_wholly_unknown_tags_skipped if {
	result := terraform.deny with input as unknown_tags_all_plan(null, true)
	count(result) == 0
}

test_deleted_resource_ignored if {
	result := terraform.deny with input as plan("aws_ebs_volume", ["delete"], {"type": "gp2", "tags_all": {}})
	count(result) == 0
}

test_data_source_ignored if {
	p := {"resource_changes": [{
		"address": "data.aws_ebs_volume.this",
		"mode": "data",
		"type": "aws_ebs_volume",
		"change": {"actions": ["create"], "after": {"type": "gp2", "tags_all": {}}},
	}]}
	result := terraform.deny with input as p
	count(result) == 0
}

# --- storage ---

test_gp2_volume_denied if {
	result := terraform.deny with input as plan("aws_ebs_volume", ["create"], tagged({"type": "gp2"}))
	result == {"`aws_ebs_volume.this` uses gp2; use gp3 (cheaper and faster)"}
}

test_gp2_root_device_denied if {
	after := tagged({"instance_type": "t4g.micro", "root_block_device": [{"volume_type": "gp2"}]})
	result := terraform.deny with input as plan("aws_instance", ["create"], after)
	result == {"`aws_instance.this` has a gp2 root_block_device; use gp3 (cheaper and faster)"}
}

test_gp3_root_device_allowed if {
	after := tagged({"instance_type": "t4g.micro", "root_block_device": [{"volume_type": "gp3"}]})
	result := terraform.deny with input as plan("aws_instance", ["create"], after)
	count(result) == 0
}

test_gp2_database_denied if {
	after := tagged({"instance_class": "db.t4g.micro", "storage_type": "gp2"})
	result := terraform.deny with input as plan("aws_db_instance", ["create"], after)
	count(result) == 1
}

test_log_group_without_retention_denied if {
	result := terraform.deny with input as plan("aws_cloudwatch_log_group", ["create"], tagged({"retention_in_days": 0}))
	result == {"`aws_cloudwatch_log_group.this` never expires logs; set retention_in_days"}
}

test_log_group_null_retention_denied if {
	result := terraform.deny with input as plan("aws_cloudwatch_log_group", ["create"], tagged({"retention_in_days": null}))
	count(result) == 1
}

test_log_group_with_retention_allowed if {
	result := terraform.deny with input as plan("aws_cloudwatch_log_group", ["create"], tagged({"retention_in_days": 14}))
	count(result) == 0
}

# --- compute ---

test_large_instance_warned if {
	result := terraform.warn with input as plan("aws_instance", ["create"], tagged({"instance_type": "m5.2xlarge"}))
	count(result) == 1
}

test_small_instance_allowed if {
	result := terraform.warn with input as plan("aws_instance", ["update"], tagged({"instance_type": "t4g.small"}))
	count(result) == 0
}

test_large_database_warned if {
	result := terraform.warn with input as plan("aws_db_instance", ["create"], tagged({"instance_class": "db.m5.large"}))
	count(result) == 1
}

test_multi_az_outside_production_warned if {
	after := tagged({"instance_class": "db.t4g.micro", "multi_az": true})
	result := terraform.warn with input as plan("aws_db_instance", ["create"], after)
	count(result) == 1
}

test_multi_az_in_production_allowed if {
	tags := object.union(good_tags, {"Environment": "Prod"})
	after := {"instance_class": "db.t4g.micro", "multi_az": true, "tags_all": tags}
	result := terraform.warn with input as plan("aws_db_instance", ["create"], after)
	count(result) == 0
}

# --- network ---

test_new_nat_gateway_warned if {
	result := terraform.warn with input as plan("aws_nat_gateway", ["create"], tagged({}))
	count(result) == 1
}

test_existing_nat_gateway_update_allowed if {
	result := terraform.warn with input as plan("aws_nat_gateway", ["update"], tagged({}))
	count(result) == 0
}
