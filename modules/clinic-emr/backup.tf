resource "aws_backup_vault" "clinic_emr" {
  name        = "${local.name_prefix}-vault"
  kms_key_arn = var.kms_key_arn

  tags = local.common_tags
}

resource "aws_backup_plan" "clinic_emr" {
  name = "${local.name_prefix}-daily"

  rule {
    rule_name         = "daily-35-day-retention"
    target_vault_name = aws_backup_vault.clinic_emr.name
    schedule          = "cron(0 18 * * ? *)"

    lifecycle {
      delete_after = 35
    }

    recovery_point_tags = local.common_tags
  }

  tags = local.common_tags
}

resource "aws_backup_selection" "clinic_emr" {
  name         = "${local.name_prefix}-protected-resources"
  plan_id      = aws_backup_plan.clinic_emr.id
  iam_role_arn = var.backup_service_role_arn

  resources = compact([
    aws_instance.application.arn,
    aws_db_instance.database.arn,
    var.existing_fsx_arn,
  ])
}
