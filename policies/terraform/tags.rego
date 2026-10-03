package terraform

# Untagged resources cannot be attributed to an owner or cost centre, so every
# taggable resource must carry the required tags (directly or via default_tags).

# A resource type is taggable if the provider exposes tags_all on it.
taggable(rc) if "tags_all" in object.keys(rc.change.after)

taggable(rc) if "tags_all" in object.keys(object.get(rc.change, "after_unknown", {}))

# tags_all is the merge of the resource's tags and the provider's default_tags.
# The provider leaves it unknown at plan time when a resource has no tags at
# all (the common case for an untagged resource) or when a tag value is only
# known at apply time. In that case fall back to the resource's own tags.
effective_tags(rc) := tags if {
	tags := rc.change.after.tags_all
	is_object(tags)
} else := tags if {
	tags := rc.change.after.tags
	is_object(tags)
} else := {}

has_tag(rc, key) if effective_tags(rc)[key] != ""

# A tag whose value is not known until apply is present, just not readable.
has_tag(rc, key) if rc.change.after_unknown.tags[key] == true

has_tag(rc, _) if rc.change.after_unknown.tags == true

deny contains msg if {
	some rc in changes
	taggable(rc)
	missing := [key | some key in data.finops.required_tags; not has_tag(rc, key)]
	count(missing) > 0
	msg := sprintf("`%s` is missing required tags: %s", [rc.address, concat(", ", missing)])
}
