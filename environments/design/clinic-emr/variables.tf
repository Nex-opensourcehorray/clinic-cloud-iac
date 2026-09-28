variable "database_master_password_wo" {
  description = "Validation-only ephemeral placeholder supplied through the process environment; never persist it"
  type        = string
  sensitive   = true
  ephemeral   = true
}
