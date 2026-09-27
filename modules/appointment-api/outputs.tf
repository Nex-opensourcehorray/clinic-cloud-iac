output "api_id" {
  description = "Appointment API REST API identifier"
  value       = aws_api_gateway_rest_api.this.id
}

output "api_invoke_url" {
  description = "Nonproduction Appointment API stage invocation URL"
  value       = aws_api_gateway_stage.this.invoke_url
}

output "intake_lambda_arn" {
  description = "Intake Lambda ARN"
  value       = aws_lambda_function.intake.arn
}

output "worker_lambda_arn" {
  description = "Worker Lambda ARN"
  value       = aws_lambda_function.worker.arn
}

output "reconciler_lambda_arn" {
  description = "Reconciler Lambda ARN"
  value       = aws_lambda_function.reconciler.arn
}

output "workflow_table_name" {
  description = "DynamoDB workflow-state table name"
  value       = aws_dynamodb_table.workflow.name
}

output "work_queue_arn" {
  description = "Appointment work queue ARN"
  value       = aws_sqs_queue.work.arn
}

output "dead_letter_queue_arn" {
  description = "Appointment DLQ ARN"
  value       = aws_sqs_queue.dead_letter.arn
}

output "web_acl_arn" {
  description = "Regional WAFv2 Web ACL ARN"
  value       = aws_wafv2_web_acl.this.arn
}

output "alert_topic_arn" {
  description = "Encrypted Appointment API operational alarm-routing topic ARN"
  value       = aws_sns_topic.alerts.arn
}

output "operations_dashboard_name" {
  description = "Appointment API operational CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.operations.dashboard_name
}
