package terraform

# A NAT gateway bills by the hour whether or not anything uses it (roughly
# $40/month in ap-south-1 before data processing), and is the most common
# source of surprise charges in small accounts.
warn contains msg if {
	some rc in creates
	rc.type == "aws_nat_gateway"
	msg := sprintf("`%s` adds a NAT gateway (about $40/month before data charges); consider VPC endpoints or a public subnet", [rc.address])
}
