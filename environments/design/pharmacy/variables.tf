variable "database_master_password_wo" {
  description = "Validation-only ephemeral input; never store a value in files or state"
  type        = string
  sensitive   = true
  ephemeral   = true
}
