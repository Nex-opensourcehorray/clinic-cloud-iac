output "aws_account_id" {
  description = "AWS account currently used by Terraform"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region currently used by Terraform"
  value       = data.aws_region.current.region
}

output "nonprod_vpc_id" {
  description = "Existing NonProduction VPC ID"
  value       = data.aws_vpc.clinic_nonprod.id
}

output "nonprod_vpc_cidr" {
  description = "Existing NonProduction VPC CIDR"
  value       = data.aws_vpc.clinic_nonprod.cidr_block
}

output "name_prefix" {
  description = "Standard resource naming prefix"
  value       = local.name_prefix
}

output "wave1_training_parameter_arn" {
  description = "ARN of the Terraform-managed Wave 1 training parameter"
  value       = aws_ssm_parameter.wave1_training.arn
}