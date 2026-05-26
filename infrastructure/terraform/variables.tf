variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "finparse"
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude Vision"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "finparse"
}

variable "db_password" {
  description = "RDS master password"
  type        = string
  sensitive   = true
}

variable "api_key_salt" {
  description = "Salt for API key hashing (hex string)"
  type        = string
  sensitive   = true
}
