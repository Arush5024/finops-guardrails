output "arn" {
  description = "ARN of the function."
  value       = aws_lambda_function.this.arn
}

output "function_name" {
  description = "Name of the function."
  value       = aws_lambda_function.this.function_name
}

output "role_arn" {
  description = "ARN of the function's execution role."
  value       = aws_iam_role.this.arn
}
