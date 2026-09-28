resource "aws_cloudwatch_metric_alarm" "application_status" {
  alarm_name          = "${local.name_prefix}-app-status-check"
  alarm_description   = "Clinic and EMR application EC2 status-check failure"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = { InstanceId = aws_instance.application.id }
  tags       = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "database_cpu" {
  alarm_name          = "${local.name_prefix}-db-cpu"
  alarm_description   = "Sustained Clinic and EMR MySQL CPU utilization"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = { DBInstanceIdentifier = aws_db_instance.database.identifier }
  tags       = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "database_free_storage" {
  alarm_name          = "${local.name_prefix}-db-free-storage"
  alarm_description   = "Low Clinic and EMR MySQL free storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 3
  threshold           = 5368709120
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = { DBInstanceIdentifier = aws_db_instance.database.identifier }
  tags       = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dms_cdc_source_lag" {
  alarm_name          = "${local.name_prefix}-dms-cdc-source-lag"
  alarm_description   = "DMS source CDC lag requires owner-defined cutover threshold"
  namespace           = "AWS/DMS"
  metric_name         = "CDCLatencySource"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ReplicationInstanceIdentifier = aws_dms_replication_instance.migration.replication_instance_id
    ReplicationTaskIdentifier     = aws_dms_replication_task.migration.replication_task_id
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dms_cdc_target_lag" {
  alarm_name          = "${local.name_prefix}-dms-cdc-target-lag"
  alarm_description   = "DMS target CDC lag requires owner-defined cutover threshold"
  namespace           = "AWS/DMS"
  metric_name         = "CDCLatencyTarget"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ReplicationInstanceIdentifier = aws_dms_replication_instance.migration.replication_instance_id
    ReplicationTaskIdentifier     = aws_dms_replication_task.migration.replication_task_id
  }

  tags = local.common_tags
}
