resource "aws_backup_vault" "pharmacy" {
  name        = "${local.name_prefix}-vault"
  kms_key_arn = var.kms_key_arn

  tags = local.common_tags
}

resource "aws_backup_plan" "pharmacy" {
  name = "${local.name_prefix}-daily"

  rule {
    rule_name         = "daily-35-day-retention"
    target_vault_name = aws_backup_vault.pharmacy.name
    schedule          = "cron(0 18 * * ? *)"

    lifecycle {
      delete_after = 35
    }

    recovery_point_tags = local.common_tags
  }

  tags = local.common_tags
}

resource "aws_backup_selection" "pharmacy" {
  name         = "${local.name_prefix}-protected-resources"
  plan_id      = aws_backup_plan.pharmacy.id
  iam_role_arn = var.backup_service_role_arn

  resources = [
    aws_instance.application.arn,
    aws_db_instance.database.arn,
  ]
}
