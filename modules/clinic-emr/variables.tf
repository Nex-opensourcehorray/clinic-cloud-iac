variable "resource_name_prefix" {
  description = "Naming prefix for the Clinic/EMR design resources"
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

variable "dns_resolver_cidr" {
  description = "Exact private DNS resolver CIDR required by application and DMS connectivity"
  type        = string

  validation {
    condition     = can(cidrnetmask(var.dns_resolver_cidr)) && var.dns_resolver_cidr != "0.0.0.0/0"
    error_message = "dns_resolver_cidr must be a valid non-default-route CIDR."
  }
}

variable "application_ami_id" {
  description = "Owner-approved patched application AMI identifier"
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]+$", var.application_ami_id))
    error_message = "application_ami_id must be a valid AMI identifier."
  }
}

variable "application_instance_type" {
  description = "Cost-conscious application instance type for the conceptual nonproduction design"
  type        = string
  default     = "t3.small"
}

variable "application_instance_profile_name" {
  description = "Name of the externally governed EC2 instance profile"
  type        = string
}

variable "application_role_arn" {
  description = "ARN of the externally governed application role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.application_role_arn))
    error_message = "application_role_arn must be a valid IAM role ARN."
  }
}

variable "source_database_cidrs" {
  description = "Exact private source MySQL CIDRs reachable by DMS on TCP/3306"
  type        = list(string)

  validation {
    condition     = length(var.source_database_cidrs) > 0 && alltrue([for cidr in var.source_database_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "source_database_cidrs must contain valid, non-default-route CIDRs."
  }
}

variable "integration_https_cidrs" {
  description = "Exact controlled-egress CIDRs for required Clinic/EMR integrations"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.integration_https_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "integration_https_cidrs must contain valid, non-default-route CIDRs."
  }
}

variable "service_endpoint_security_group_id" {
  description = "Optional SG for externally managed SSM, logging, KMS, and Secrets Manager interface endpoints"
  type        = string
  default     = null
  nullable    = true
}

variable "existing_fsx_security_group_id" {
  description = "Optional SG of an externally managed FSx share when vendor evidence requires SMB"
  type        = string
  default     = null
  nullable    = true
}

variable "existing_fsx_arn" {
  description = "Optional ARN of an externally managed FSx filesystem included in conceptual backup coverage"
  type        = string
  default     = null
  nullable    = true
}

variable "database_master_username" {
  description = "Non-secret MySQL bootstrap administrator name"
  type        = string
  default     = "clinic_emr_admin"
}

variable "database_master_password_wo" {
  description = "Ephemeral write-only MySQL bootstrap password; never store in tfvars, state, Git, logs, or evidence"
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "database_master_password_wo_version" {
  description = "Monotonic version used to rotate the write-only bootstrap password"
  type        = number
  default     = 1
}

variable "database_credentials_secret_arn" {
  description = "ARN of the externally governed Clinic/EMR application database secret"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.database_credentials_secret_arn))
    error_message = "database_credentials_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "dms_source_secret_arn" {
  description = "ARN of the externally governed DMS source endpoint secret"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.dms_source_secret_arn))
    error_message = "dms_source_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "dms_target_secret_arn" {
  description = "ARN of the externally governed DMS target endpoint secret"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.dms_target_secret_arn))
    error_message = "dms_target_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "dms_secrets_access_role_arn" {
  description = "ARN of the externally governed DMS role restricted to the two endpoint secrets and KMS key"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.dms_secrets_access_role_arn))
    error_message = "dms_secrets_access_role_arn must be a valid IAM role ARN."
  }
}

variable "dms_source_certificate_arn" {
  description = "ARN of an externally imported DMS certificate used to verify the source MySQL server"
  type        = string
}

variable "dms_target_certificate_arn" {
  description = "ARN of an externally imported DMS certificate used to verify RDS MySQL"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of an externally governed KMS key for EC2, RDS, DMS, logs, and backups"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:kms:[a-z0-9-]+:[0-9]{12}:key/[0-9a-f-]+$", var.kms_key_arn))
    error_message = "kms_key_arn must be a valid KMS key ARN."
  }
}

variable "backup_service_role_arn" {
  description = "ARN of the externally governed AWS Backup service role"
  type        = string
}

variable "alarm_topic_arn" {
  description = "Optional externally governed SNS topic ARN for operational alarms"
  type        = string
  default     = null
  nullable    = true
}

variable "database_name" {
  description = "Target application database name; source schema compatibility remains unverified"
  type        = string
  default     = "clinic_emr"
}

variable "source_schema_name" {
  description = "Exact source schema selected by DMS after schema inventory"
  type        = string
  default     = "clinic_emr"
}

variable "database_engine_version" {
  description = "Conceptual RDS MySQL major version; requires vendor and source confirmation"
  type        = string
  default     = "8.0"
}

variable "database_parameter_group_family" {
  description = "Parameter-group family matching the selected MySQL major version"
  type        = string
  default     = "mysql8.0"
}

variable "database_instance_class" {
  description = "Small conceptual shared Clinic/EMR database class"
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

variable "database_backup_retention_days" {
  description = "Automated RDS backup retention for the conceptual design"
  type        = number
  default     = 7
}

variable "dms_replication_instance_class" {
  description = "Conceptual DMS replication instance class; source metrics must validate sizing"
  type        = string
  default     = "dms.t3.small"
}

variable "dms_allocated_storage_gib" {
  description = "Conceptual DMS replication storage in GiB"
  type        = number
  default     = 50
}

variable "log_retention_days" {
  description = "Retention for operational logs that must exclude clinical payloads"
  type        = number
  default     = 90
}

variable "common_tags" {
  description = "Common portfolio tags"
  type        = map(string)
}

check "external_fsx_inputs_are_consistent" {
  assert {
    condition = (
      (var.existing_fsx_security_group_id == null && var.existing_fsx_arn == null) ||
      (var.existing_fsx_security_group_id != null && var.existing_fsx_arn != null)
    )
    error_message = "existing_fsx_security_group_id and existing_fsx_arn must be supplied together."
  }
}

check "no_default_route_allowlists" {
  assert {
    condition = (
      !contains(var.source_database_cidrs, "0.0.0.0/0") &&
      !contains(var.integration_https_cidrs, "0.0.0.0/0")
    )
    error_message = "Source and integration connectivity must never use an unrestricted IPv4 CIDR."
  }
}
