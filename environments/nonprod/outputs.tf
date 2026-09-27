output "aws_account_id" {
  description = "AWS account currently used by Terraform"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region currently used by Terraform"
  value       = data.aws_region.current.region
}

output "nonprod_vpc_id" {
  description = "Terraform-managed NonProduction VPC ID"
  value       = module.network.vpc_id
}

output "nonprod_vpc_cidr" {
  description = "CIDR block of the Terraform-managed NonProduction VPC"
  value       = module.network.vpc_cidr
}

output "name_prefix" {
  description = "Standard resource naming prefix"
  value       = local.name_prefix
}

output "wave1_training_parameter_arn" {
  description = "ARN of the Terraform-managed Wave 1 training parameter"
  value       = aws_ssm_parameter.wave1_training.arn
}

output "nonprod_subnet_ids" {
  description = "Terraform-managed NonProduction subnet IDs"
  value       = module.network.subnet_ids
}

output "nonprod_route_table_ids" {
  value = module.network.route_table_ids
}

output "nonprod_internet_gateway_id" {
  value = module.network.internet_gateway_id
}

output "nonprod_security_group_ids" {
  description = "Explicit security group boundaries for the non-production VPC"
  value       = module.network.security_group_ids
}

output "nonprod_s3_gateway_endpoint_id" {
  description = "S3 Gateway VPC Endpoint managed by Terraform for NonProd private routing."
  value       = module.network.s3_gateway_endpoint_id
}

output "appointment_api_invoke_url" {
  description = "Nonproduction Appointment API invocation URL"
  value       = module.appointment_api.api_invoke_url
}

output "appointment_workflow_table_name" {
  description = "Appointment workflow DynamoDB table name"
  value       = module.appointment_api.workflow_table_name
}

output "appointment_work_queue_arn" {
  description = "Appointment work queue ARN"
  value       = module.appointment_api.work_queue_arn
}

output "appointment_dead_letter_queue_arn" {
  description = "Appointment dead-letter queue ARN"
  value       = module.appointment_api.dead_letter_queue_arn
}

output "appointment_alert_topic_arn" {
  description = "Encrypted Appointment API operational alarm-routing topic ARN"
  value       = module.appointment_api.alert_topic_arn
}

output "appointment_operations_dashboard_name" {
  description = "Appointment API operational CloudWatch dashboard name"
  value       = module.appointment_api.operations_dashboard_name
}
