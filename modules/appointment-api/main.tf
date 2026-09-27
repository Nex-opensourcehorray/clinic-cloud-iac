locals {
  name_prefix = "${var.resource_name_prefix}-appointment-api"

  lambda_source_code_hash = var.lambda_source_code_hash != null ? var.lambda_source_code_hash : (
    fileexists(var.lambda_package_path) ? filebase64sha256(var.lambda_package_path) : null
  )

  common_tags = merge(
    var.common_tags,
    {
      Component = "appointment-api"
      ManagedBy = "Terraform"
      Wave      = "3"
    }
  )
}
