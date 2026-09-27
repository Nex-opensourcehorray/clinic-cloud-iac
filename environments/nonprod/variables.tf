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

variable "appointment_api_hmac_secret_arn" {
  description = "ARN of the externally managed nonproduction Appointment API HMAC secret"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.appointment_api_hmac_secret_arn))
    error_message = "appointment_api_hmac_secret_arn must be a non-empty AWS Secrets Manager secret ARN."
  }
}

variable "appointment_api_intake_role_arn" {
  description = "ARN of the externally managed nonproduction Appointment API intake Lambda role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.appointment_api_intake_role_arn))
    error_message = "appointment_api_intake_role_arn must be a valid IAM role ARN."
  }
}

variable "appointment_api_worker_role_arn" {
  description = "ARN of the externally managed nonproduction Appointment API worker Lambda role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.appointment_api_worker_role_arn))
    error_message = "appointment_api_worker_role_arn must be a valid IAM role ARN."
  }
}

variable "appointment_api_reconciler_role_arn" {
  description = "ARN of the externally managed nonproduction Appointment API reconciler Lambda role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.appointment_api_reconciler_role_arn))
    error_message = "appointment_api_reconciler_role_arn must be a valid IAM role ARN."
  }
}

variable "appointment_api_api_gateway_logs_role_arn" {
  description = "ARN of the externally managed nonproduction API Gateway CloudWatch logging role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.appointment_api_api_gateway_logs_role_arn))
    error_message = "appointment_api_api_gateway_logs_role_arn must be a valid IAM role ARN."
  }
}

variable "training_parameter_name" {
  description = "Name of the non-sensitive SSM parameter used for Terraform lifecycle training"
  type        = string
}

variable "training_parameter_value" {
  description = "Non-sensitive value stored in the Terraform training parameter"
  type        = string
}
