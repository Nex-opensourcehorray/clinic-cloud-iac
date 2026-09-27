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

variable "alarm_actions" {
  description = "Optional SNS topic ARNs for alarm notifications"
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = "Optional SNS topic ARNs for alarm recovery notifications"
  type        = list(string)
  default     = []
}
