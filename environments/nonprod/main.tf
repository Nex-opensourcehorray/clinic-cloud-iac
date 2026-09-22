data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_vpc" "clinic_nonprod" {
  filter {
    name   = "tag:Name"
    values = ["clinic-nonproduction-vpc"]
  }
}

resource "aws_ssm_parameter" "wave1_training" {
  name        = var.training_parameter_name
  description = "Wave 1 Terraform lifecycle training parameter"
  type        = "String"
  value       = var.training_parameter_value

  tags = local.common_tags
}
