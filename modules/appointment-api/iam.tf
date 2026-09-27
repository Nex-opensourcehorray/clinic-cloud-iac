# The four Appointment API IAM roles are externally managed prerequisites.
# Terraform consumes their approved ARNs but does not read or manage their
# trust policies, permissions, permissions boundaries, or lifecycle.

resource "aws_api_gateway_account" "this" {
  cloudwatch_role_arn = var.api_gateway_logs_role_arn
}
