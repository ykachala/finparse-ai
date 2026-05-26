output "api_endpoint" {
  description = "HTTP API endpoint URL"
  value       = aws_apigatewayv2_api.main.api_endpoint
}

output "s3_bucket_name" {
  description = "S3 bucket for document storage"
  value       = aws_s3_bucket.documents.bucket
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.api.function_name
}
