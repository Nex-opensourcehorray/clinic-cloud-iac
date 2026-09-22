variable "aws_region" {
  description = "AWS Region hosting the NonProduction Terraform state backend"
  type        = string
}

variable "project_name" {
  description = "Logical project name"
  type        = string
}

variable "environment" {
  description = "Environment whose Terraform state will be stored"
  type        = string
}