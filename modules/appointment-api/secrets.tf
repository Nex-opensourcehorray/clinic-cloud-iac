# EXTERNALLY MANAGED OPERATIONAL DEPENDENCY
#
# Terraform intentionally does not create, import, delete, or read the
# Appointment API HMAC secret. The secret ARN is supplied through
# var.hmac_secret_arn solely for the intake Lambda environment and its exact
# secretsmanager:GetSecretValue IAM resource scope. Secret metadata and value
# lifecycle remain in a separately approved out-of-band operational process.
