locals {
  monitored_lambda_functions = {
    intake     = aws_lambda_function.intake.function_name
    worker     = aws_lambda_function.worker.function_name
    reconciler = aws_lambda_function.reconciler.function_name
  }

  workflow_operational_alarms = {
    stale_queue_state = {
      metric_name = "StaleQueueState"
      description = "Appointment workflow contains stale queue or processing state"
    }
    reconciliation_failure = {
      metric_name = "ReconciliationFailure"
      description = "Appointment workflow reconciliation failed or remained uncertain"
    }
    manual_review_backlog = {
      metric_name = "ManualReviewBacklog"
      description = "Appointment workflow has requests awaiting manual operational review"
    }
    processing_lease_expired = {
      metric_name = "ProcessingLeaseExpired"
      description = "Appointment workflow processing ownership lease expired"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "workflow_operational" {
  for_each = local.workflow_operational_alarms

  alarm_name          = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  alarm_description   = each.value.description
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = each.value.metric_name
  namespace           = "Clinic/AppointmentApi"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.monitored_lambda_functions

  alarm_name          = "${local.name_prefix}-${each.key}-errors"
  alarm_description   = "Appointment API ${each.key} Lambda reported errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = local.monitored_lambda_functions

  alarm_name          = "${local.name_prefix}-${each.key}-throttles"
  alarm_description   = "Appointment API ${each.key} Lambda was throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name_prefix}-api-5xx"
  alarm_description   = "Appointment API returned server errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = aws_api_gateway_rest_api.this.name
    Stage   = aws_api_gateway_stage.this.stage_name
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "work_queue_age" {
  alarm_name          = "${local.name_prefix}-work-queue-age"
  alarm_description   = "Oldest Appointment API work message exceeds five minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 300
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.work.name
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dead_letter_messages" {
  alarm_name          = "${local.name_prefix}-dlq-messages"
  alarm_description   = "Appointment API dead-letter queue contains a message"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dead_letter.name
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_system_errors" {
  alarm_name          = "${local.name_prefix}-dynamodb-system-errors"
  alarm_description   = "Appointment workflow table reported system errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "SystemErrors"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.workflow.name
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = local.common_tags
}
