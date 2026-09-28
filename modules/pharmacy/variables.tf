variable "resource_name_prefix" {
  description = "Naming prefix for the Pharmacy design resources"
  type        = string
}

variable "vpc_id" {
  description = "Existing VPC identifier used by the design"
  type        = string

  validation {
    condition     = can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "vpc_id must be a valid VPC identifier."
  }
}

variable "private_subnet_ids" {
  description = "Two existing private subnet identifiers in distinct Availability Zones"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) == 2 && alltrue([for id in var.private_subnet_ids : can(regex("^subnet-[0-9a-f]+$", id))])
    error_message = "private_subnet_ids must contain exactly two valid subnet identifiers."
  }
}

variable "application_ami_id" {
  description = "Owner-approved patched Windows Server AMI identifier"
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]+$", var.application_ami_id))
    error_message = "application_ami_id must be a valid AMI identifier."
  }
}

variable "application_instance_type" {
  description = "Cost-conscious EC2 instance type for the conceptual nonproduction pilot"
  type        = string
  default     = "t3.small"
}

variable "application_instance_profile_name" {
  description = "Name of the externally governed EC2 instance profile providing SSM and telemetry permissions"
  type        = string
}

variable "application_role_arn" {
  description = "ARN of the externally governed EC2 role associated with the instance profile"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.application_role_arn))
    error_message = "application_role_arn must be a valid IAM role ARN."
  }
}

variable "database_credentials_secret_arn" {
  description = "ARN of the externally governed secret containing Pharmacy database credentials"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.database_credentials_secret_arn))
    error_message = "database_credentials_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "database_master_username" {
  description = "Non-secret SQL Server bootstrap administrator name"
  type        = string
  default     = "pharmacy_admin"
}

variable "database_master_password_wo" {
  description = "Ephemeral write-only SQL Server bootstrap password; never store in tfvars, state, Git, logs, or evidence"
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "database_master_password_wo_version" {
  description = "Monotonic version used to rotate the write-only bootstrap password"
  type        = number
  default     = 1
}

variable "kms_key_arn" {
  description = "ARN of an externally governed KMS key for EBS, RDS, logs, and backup encryption"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:kms:[a-z0-9-]+:[0-9]{12}:key/[0-9a-f-]+$", var.kms_key_arn))
    error_message = "kms_key_arn must be a valid KMS key ARN."
  }
}

variable "backup_service_role_arn" {
  description = "ARN of the externally governed AWS Backup service role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.backup_service_role_arn))
    error_message = "backup_service_role_arn must be a valid IAM role ARN."
  }
}

variable "alarm_topic_arn" {
  description = "Optional externally governed SNS topic ARN for operational alarms"
  type        = string
  default     = null
  nullable    = true
}

variable "provider_https_cidrs" {
  description = "Exact provider or controlled-egress CIDRs permitted for outbound HTTPS; empty until the provider contract is known"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.provider_https_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "provider_https_cidrs must contain valid, non-default-route CIDRs."
  }
}

variable "ssm_endpoint_security_group_id" {
  description = "Security group ID for externally managed SSM interface endpoints; null until those endpoints exist"
  type        = string
  default     = null
  nullable    = true
}

variable "enable_directory_authentication" {
  description = "Enable SQL Server directory authentication only after edition, region, DNS, and trust prerequisites are validated"
  type        = bool
  default     = false
}

variable "directory_id" {
  description = "Existing AWS Managed Microsoft AD identifier used only when directory authentication is validated"
  type        = string
  default     = null
  nullable    = true
}

variable "directory_iam_role_name" {
  description = "Externally governed RDS directory integration role name"
  type        = string
  default     = null
  nullable    = true
}

variable "database_instance_class" {
  description = "Small conceptual nonproduction SQL Server instance class"
  type        = string
  default     = "db.t3.small"
}

variable "database_allocated_storage_gib" {
  description = "Initial gp3 database storage in GiB"
  type        = number
  default     = 20

  validation {
    condition     = var.database_allocated_storage_gib >= 20
    error_message = "database_allocated_storage_gib must be at least 20 GiB."
  }
}

variable "backup_retention_days" {
  description = "Automated RDS backup retention for the conceptual nonproduction design"
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 7 and 35 days."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention"
  type        = number
  default     = 90
}

variable "common_tags" {
  description = "Common portfolio tags"
  type        = map(string)
}

check "directory_inputs_are_complete" {
  assert {
    condition = !var.enable_directory_authentication || (
      var.directory_id != null && var.directory_iam_role_name != null
    )
    error_message = "directory_id and directory_iam_role_name are required when directory authentication is enabled."
  }
}
