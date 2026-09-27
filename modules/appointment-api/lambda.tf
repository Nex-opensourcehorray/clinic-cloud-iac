resource "aws_lambda_function" "intake" {
  function_name = "${local.name_prefix}-intake"
  description   = "Nonproduction authenticated Appointment API intake"
  role          = aws_iam_role.intake.arn
  runtime       = "python3.13"
  handler       = "intake.handler.lambda_handler"

  filename         = var.lambda_package_path
  source_code_hash = local.lambda_source_code_hash

  architectures                  = ["x86_64"]
  memory_size                    = 256
  timeout                        = var.intake_timeout_seconds
  reserved_concurrent_executions = 5

  environment {
    variables = {
      ENVIRONMENT                = var.environment
      HMAC_SECRET_ARN            = aws_secretsmanager_secret.hmac.arn
      IDEMPOTENCY_TTL_SECONDS    = tostring(var.idempotency_ttl_days * 86400)
      MAXIMUM_BODY_BYTES         = tostring(var.maximum_request_body_bytes)
      MAXIMUM_CLOCK_SKEW_SECONDS = tostring(var.maximum_clock_skew_seconds)
      NONCE_TTL_SECONDS          = tostring(var.nonce_ttl_seconds)
      WORKFLOW_TABLE_NAME        = aws_dynamodb_table.workflow.name
      WORK_QUEUE_URL             = aws_sqs_queue.work.id
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.intake,
    aws_iam_role_policy.intake,
  ]
}

resource "aws_lambda_function" "worker" {
  function_name = "${local.name_prefix}-worker"
  description   = "Nonproduction Appointment API queue worker foundation; no clinical-system action"
  role          = aws_iam_role.worker.arn
  runtime       = "python3.13"
  handler       = "worker.handler.lambda_handler"

  filename         = var.lambda_package_path
  source_code_hash = local.lambda_source_code_hash

  architectures                  = ["x86_64"]
  memory_size                    = 256
  timeout                        = var.worker_timeout_seconds
  reserved_concurrent_executions = 5

  environment {
    variables = {
      ENVIRONMENT     = var.environment
      FOUNDATION_MODE = "true"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.worker,
    aws_iam_role_policy.worker,
  ]
}

resource "aws_lambda_function" "reconciler" {
  function_name = "${local.name_prefix}-reconciler"
  description   = "Nonproduction Appointment API reconciliation foundation; no workflow mutation"
  role          = aws_iam_role.reconciler.arn
  runtime       = "python3.13"
  handler       = "reconciler.handler.lambda_handler"

  filename         = var.lambda_package_path
  source_code_hash = local.lambda_source_code_hash

  architectures                  = ["x86_64"]
  memory_size                    = 128
  timeout                        = var.reconciler_timeout_seconds
  reserved_concurrent_executions = 1

  environment {
    variables = {
      ENVIRONMENT     = var.environment
      FOUNDATION_MODE = "true"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.reconciler,
    aws_iam_role_policy.reconciler,
  ]
}

resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn = aws_sqs_queue.work.arn
  function_name    = aws_lambda_function.worker.arn

  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
  enabled                            = true
}

resource "aws_cloudwatch_event_rule" "reconciler" {
  name                = "${local.name_prefix}-reconciler"
  description         = "Invokes the foundation reconciler on a fixed schedule"
  schedule_expression = "rate(5 minutes)"

  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "reconciler" {
  rule      = aws_cloudwatch_event_rule.reconciler.name
  target_id = "appointment-reconciler"
  arn       = aws_lambda_function.reconciler.arn
}

resource "aws_lambda_permission" "reconciler_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reconciler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reconciler.arn
}
