locals {
  name_prefix = var.resource_name_prefix

  common_tags = merge(
    var.common_tags,
    {
      Component          = "clinic-emr"
      DataClassification = "restricted-clinical"
      DeploymentStatus   = "design-only"
      ManagedBy          = "Terraform"
      Wave               = "5"
    }
  )

  alarm_actions = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}
