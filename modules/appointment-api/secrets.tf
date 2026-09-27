# Terraform owns only the secret metadata. The HMAC key document must be
# provisioned through a separately approved out-of-band process.
resource "aws_secretsmanager_secret" "hmac" {
  name                    = "${local.name_prefix}/hmac-keys"
  description             = "Appointment API HMAC key ring; value managed outside Terraform"
  recovery_window_in_days = 30

  tags = merge(
    local.common_tags,
    {
      DataPurpose = "appointment-api-request-authentication"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}
