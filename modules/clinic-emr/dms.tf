resource "aws_dms_replication_subnet_group" "migration" {
  replication_subnet_group_description = "Private Clinic and EMR full-load and CDC design"
  replication_subnet_group_id          = "${local.name_prefix}-dms"
  subnet_ids                           = var.private_subnet_ids

  tags = local.common_tags
}

resource "aws_dms_replication_instance" "migration" {
  replication_instance_id     = "${local.name_prefix}-dms"
  replication_instance_class  = var.dms_replication_instance_class
  allocated_storage           = var.dms_allocated_storage_gib
  replication_subnet_group_id = aws_dms_replication_subnet_group.migration.id
  vpc_security_group_ids      = [aws_security_group.dms.id]
  publicly_accessible         = false
  multi_az                    = false
  auto_minor_version_upgrade  = true
  apply_immediately           = false
  kms_key_arn                 = var.kms_key_arn

  tags = local.common_tags
}

resource "aws_dms_endpoint" "source" {
  endpoint_id                     = "${local.name_prefix}-source"
  endpoint_type                   = "source"
  engine_name                     = "mysql"
  database_name                   = var.source_schema_name
  ssl_mode                        = "verify-full"
  certificate_arn                 = var.dms_source_certificate_arn
  secrets_manager_arn             = var.dms_source_secret_arn
  secrets_manager_access_role_arn = var.dms_secrets_access_role_arn

  tags = local.common_tags
}

resource "aws_dms_endpoint" "target" {
  endpoint_id                     = "${local.name_prefix}-target"
  endpoint_type                   = "target"
  engine_name                     = "mysql"
  database_name                   = var.database_name
  ssl_mode                        = "verify-full"
  certificate_arn                 = var.dms_target_certificate_arn
  secrets_manager_arn             = var.dms_target_secret_arn
  secrets_manager_access_role_arn = var.dms_secrets_access_role_arn

  tags = local.common_tags
}

resource "aws_dms_replication_task" "migration" {
  replication_task_id      = "${local.name_prefix}-full-load-cdc"
  migration_type           = "full-load-and-cdc"
  replication_instance_arn = aws_dms_replication_instance.migration.replication_instance_arn
  source_endpoint_arn      = aws_dms_endpoint.source.endpoint_arn
  target_endpoint_arn      = aws_dms_endpoint.target.endpoint_arn

  table_mappings = jsonencode({
    rules = [
      {
        "rule-type" = "selection"
        "rule-id"   = "1"
        "rule-name" = "explicit-clinic-emr-schema"
        "object-locator" = {
          "schema-name" = var.source_schema_name
          "table-name"  = "%"
        }
        "rule-action" = "include"
      }
    ]
  })

  replication_task_settings = jsonencode({
    Logging = {
      EnableLogging = true
      LogComponents = [
        { Id = "SOURCE_UNLOAD", Severity = "LOGGER_SEVERITY_DEFAULT" },
        { Id = "TARGET_LOAD", Severity = "LOGGER_SEVERITY_DEFAULT" },
        { Id = "TASK_MANAGER", Severity = "LOGGER_SEVERITY_DEFAULT" }
      ]
    }
    FullLoadSettings = {
      CommitRate                      = 10000
      MaxFullLoadSubTasks             = 4
      StopTaskCachedChangesApplied    = false
      StopTaskCachedChangesNotApplied = false
      TargetTablePrepMode             = "DO_NOTHING"
    }
    TargetMetadata = {
      SupportLobs        = true
      FullLobMode        = false
      LimitedSizeLobMode = true
      LobMaxSize         = 32
    }
    ValidationSettings = {
      EnableValidation = true
      ThreadCount      = 5
    }
    ErrorBehavior = {
      DataErrorPolicy               = "STOP_TASK"
      DataTruncationErrorPolicy     = "STOP_TASK"
      TableErrorPolicy              = "STOP_TASK"
      RecoverableErrorCount         = 5
      RecoverableErrorInterval      = 5
      RecoverableErrorThrottling    = true
      RecoverableErrorThrottlingMax = 1800
    }
  })

  tags = local.common_tags
}
