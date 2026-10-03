output "state_bucket" {
  description = "Name of the Terraform state bucket. Put this in infra/backend.hcl."
  value       = aws_s3_bucket.state.id
}
