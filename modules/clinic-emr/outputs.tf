output "application_instance_id" {
  description = "Conceptual private Clinic and EMR application instance"
  value       = aws_instance.application.id
}

output "database_endpoint" {
  description = "Conceptual private RDS MySQL endpoint"
  value       = aws_db_instance.database.endpoint
  sensitive   = true
}

output "dms_replication_task_arn" {
  description = "Conceptual full-load and CDC task ARN"
  value       = aws_dms_replication_task.migration.replication_task_arn
}

output "application_security_group_id" {
  description = "Conceptual application security group"
  value       = aws_security_group.application.id
}

output "database_security_group_id" {
  description = "Conceptual database security group"
  value       = aws_security_group.database.id
}

output "dms_security_group_id" {
  description = "Conceptual DMS security group"
  value       = aws_security_group.dms.id
}

output "external_application_role_arn" {
  description = "Externally governed application role contract"
  value       = var.application_role_arn
}

output "external_database_secret_arn" {
  description = "Externally governed application database secret contract"
  value       = var.database_credentials_secret_arn
}

output "deployment_status" {
  description = "Permanent Wave 5 governance state"
  value       = "DESIGN VALIDATED — NOT DEPLOYED"
}
