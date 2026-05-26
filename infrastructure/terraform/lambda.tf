resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "${local.name_prefix}-lambda-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.documents.arn}/*"
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${local.name_prefix}:latest"
  timeout       = 30
  memory_size   = 1024

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DATABASE_URL         = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.endpoint}/finparse"
      SYNC_DATABASE_URL    = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.main.endpoint}/finparse"
      REDIS_URL            = "redis://localhost:6379"
      ANTHROPIC_API_KEY    = var.anthropic_api_key
      AWS_S3_BUCKET        = aws_s3_bucket.documents.bucket
      AWS_REGION           = var.aws_region
      API_KEY_SALT         = var.api_key_salt
      ENVIRONMENT          = var.environment
    }
  }

  tags = local.common_tags
}

data "aws_caller_identity" "current" {}
