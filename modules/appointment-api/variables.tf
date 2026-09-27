variable "resource_name_prefix" {
  description = "Naming prefix for Appointment API resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
}

variable "common_tags" {
  description = "Tags shared by Appointment API resources"
  type        = map(string)
}

variable "hmac_secret_arn" {
  description = "ARN of the externally managed Secrets Manager secret used for Appointment API HMAC authentication"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$", var.hmac_secret_arn))
    error_message = "hmac_secret_arn must be a non-empty AWS Secrets Manager secret ARN."
  }
}

variable "intake_role_arn" {
  description = "ARN of the externally managed Appointment API intake Lambda execution role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.intake_role_arn))
    error_message = "intake_role_arn must be a valid IAM role ARN."
  }
}

variable "worker_role_arn" {
  description = "ARN of the externally managed Appointment API worker Lambda execution role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.worker_role_arn))
    error_message = "worker_role_arn must be a valid IAM role ARN."
  }
}

variable "reconciler_role_arn" {
  description = "ARN of the externally managed Appointment API reconciler Lambda execution role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.reconciler_role_arn))
    error_message = "reconciler_role_arn must be a valid IAM role ARN."
  }
}

variable "api_gateway_logs_role_arn" {
  description = "ARN of the externally managed API Gateway CloudWatch logging role"
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.api_gateway_logs_role_arn))
    error_message = "api_gateway_logs_role_arn must be a valid IAM role ARN."
  }
}

variable "request_schema" {
  description = "JSON Schema object used by the API Gateway request model"
  type        = any
}

variable "lambda_package_path" {
  description = "Absolute path to the locally built Appointment API Lambda ZIP package"
  type        = string
}

variable "lambda_source_code_hash" {
  description = "Optional base64-encoded SHA-256 hash supplied by the build pipeline"
  type        = string
  default     = null
  nullable    = true
}

variable "stage_name" {
  description = "API Gateway deployment stage name"
  type        = string
  default     = "nonprod"
}

variable "log_retention_days" {
  description = "Retention period for Appointment API CloudWatch log groups"
  type        = number
  default     = 90

  validation {
    condition     = contains([14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch Logs-supported retention value."
  }
}

variable "api_throttle_rate_limit" {
  description = "Steady-state request rate limit for the API stage"
  type        = number
  default     = 10

  validation {
    condition     = var.api_throttle_rate_limit > 0
    error_message = "api_throttle_rate_limit must be greater than zero."
  }
}

variable "api_throttle_burst_limit" {
  description = "Burst request limit for the API stage"
  type        = number
  default     = 20

  validation {
    condition     = var.api_throttle_burst_limit > 0
    error_message = "api_throttle_burst_limit must be greater than zero."
  }
}

variable "waf_rate_limit" {
  description = "Maximum requests per WAF rate-evaluation window for a source IP"
  type        = number
  default     = 300

  validation {
    condition     = var.waf_rate_limit >= 10
    error_message = "waf_rate_limit must be at least 10."
  }
}

variable "maximum_request_body_bytes" {
  description = "Maximum Appointment API request body size inspected by the WAF rule"
  type        = number
  default     = 16384

  validation {
    condition     = var.maximum_request_body_bytes >= 1024 && var.maximum_request_body_bytes <= 65536
    error_message = "maximum_request_body_bytes must be between 1,024 and 65,536 bytes."
  }
}

variable "intake_timeout_seconds" {
  description = "Intake Lambda timeout"
  type        = number
  default     = 10
}

variable "worker_timeout_seconds" {
  description = "Worker Lambda timeout"
  type        = number
  default     = 30
}

variable "reconciler_timeout_seconds" {
  description = "Reconciler Lambda timeout"
  type        = number
  default     = 30
}

variable "queue_visibility_timeout_seconds" {
  description = "Work queue visibility timeout; configured at six times the default worker timeout"
  type        = number
  default     = 180
}

variable "idempotency_ttl_days" {
  description = "Initial retention period for idempotency records"
  type        = number
  default     = 7

  validation {
    condition     = var.idempotency_ttl_days == 7
    error_message = "The W3.2 baseline requires the accepted seven-day idempotency TTL."
  }
}

variable "maximum_clock_skew_seconds" {
  description = "Maximum accepted request timestamp skew in either direction"
  type        = number
  default     = 300

  validation {
    condition     = var.maximum_clock_skew_seconds == 300
    error_message = "The Appointment API authentication contract requires a 300-second clock skew."
  }
}

variable "nonce_ttl_seconds" {
  description = "Replay-protection nonce retention period"
  type        = number
  default     = 600

  validation {
    condition     = var.nonce_ttl_seconds >= 600
    error_message = "nonce_ttl_seconds must be at least 600 seconds."
  }
}

variable "processing_lease_seconds" {
  description = "Bounded worker and reconciler ownership lease duration"
  type        = number
  default     = 120

  validation {
    condition     = var.processing_lease_seconds >= 60 && var.processing_lease_seconds <= 900
    error_message = "processing_lease_seconds must be between 60 and 900 seconds."
  }
}

variable "reconciliation_stale_seconds" {
  description = "Age after which a QUEUE_PENDING request becomes eligible for reconciliation"
  type        = number
  default     = 300

  validation {
    condition     = var.reconciliation_stale_seconds >= 60
    error_message = "reconciliation_stale_seconds must be at least 60 seconds."
  }
}

variable "reconciliation_backoff_seconds" {
  description = "Delay before another bounded reconciliation attempt"
  type        = number
  default     = 300

  validation {
    condition     = var.reconciliation_backoff_seconds >= 60
    error_message = "reconciliation_backoff_seconds must be at least 60 seconds."
  }
}

variable "maximum_reconciliation_attempts" {
  description = "Maximum re-enqueue attempts before manual-review escalation"
  type        = number
  default     = 3

  validation {
    condition     = var.maximum_reconciliation_attempts >= 1 && var.maximum_reconciliation_attempts <= 10
    error_message = "maximum_reconciliation_attempts must be between 1 and 10."
  }
}

variable "reconciliation_batch_size" {
  description = "Maximum due requests queried per recoverable state per invocation"
  type        = number
  default     = 25

  validation {
    condition     = var.reconciliation_batch_size >= 1 && var.reconciliation_batch_size <= 100
    error_message = "reconciliation_batch_size must be between 1 and 100."
  }
}
