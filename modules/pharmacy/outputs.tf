output "application_instance_id" {
  description = "Conceptual Pharmacy application instance identifier"
  value       = aws_instance.application.id
}

output "application_security_group_id" {
  description = "Conceptual Pharmacy application security group identifier"
  value       = aws_security_group.application.id
}

output "database_endpoint" {
  description = "Conceptual private SQL Server endpoint"
  value       = aws_db_instance.database.endpoint
  sensitive   = true
}

output "database_security_group_id" {
  description = "Conceptual Pharmacy database security group identifier"
  value       = aws_security_group.database.id
}

output "external_application_role_arn" {
  description = "Externally governed EC2 role contract"
  value       = var.application_role_arn
}

output "external_database_secret_arn" {
  description = "Externally governed database credential container contract"
  value       = var.database_credentials_secret_arn
}

output "deployment_status" {
  description = "Permanent Wave 4 governance state"
  value       = "DESIGN VALIDATED — NOT DEPLOYED"
}
