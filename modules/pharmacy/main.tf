locals {
  name_prefix = var.resource_name_prefix

  common_tags = merge(
    var.common_tags,
    {
      Component          = "pharmacy"
      DataClassification = "confidential"
      DeploymentStatus   = "design-only"
      ManagedBy          = "Terraform"
      Wave               = "4"
    }
  )
}
