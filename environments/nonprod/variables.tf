variable "aws_region" {
  description = "AWS Region used by the NonProduction environment"
  type        = string
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
}

variable "project_name" {
  description = "Logical project name"
  type        = string
}

variable "training_parameter_name" {
  description = "Name of the non-sensitive SSM parameter used for Terraform lifecycle training"
  type        = string
}

variable "training_parameter_value" {
  description = "Non-sensitive value stored in the Terraform training parameter"
  type        = string
}