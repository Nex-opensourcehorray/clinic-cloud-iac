data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "AllowLambdaServiceAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "intake" {
  name               = "${local.name_prefix}-intake"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_role" "worker" {
  name               = "${local.name_prefix}-worker"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_role" "reconciler" {
  name               = "${local.name_prefix}-reconciler"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "intake" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.intake.arn}:*"]
  }

  # X-Ray write APIs do not support resource-level permissions.
  statement {
    sid    = "WriteXRayTelemetry"
    effect = "Allow"
    actions = [
      "xray:PutTelemetryRecords",
      "xray:PutTraceSegments",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "intake" {
  name   = "${local.name_prefix}-intake"
  role   = aws_iam_role.intake.id
  policy = data.aws_iam_policy_document.intake.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.worker.arn}:*"]
  }

  statement {
    sid    = "ConsumeAppointmentWork"
    effect = "Allow"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.work.arn]
  }

  # X-Ray write APIs do not support resource-level permissions.
  statement {
    sid    = "WriteXRayTelemetry"
    effect = "Allow"
    actions = [
      "xray:PutTelemetryRecords",
      "xray:PutTraceSegments",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "${local.name_prefix}-worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

data "aws_iam_policy_document" "reconciler" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.reconciler.arn}:*"]
  }

  # X-Ray write APIs do not support resource-level permissions.
  statement {
    sid    = "WriteXRayTelemetry"
    effect = "Allow"
    actions = [
      "xray:PutTelemetryRecords",
      "xray:PutTraceSegments",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "reconciler" {
  name   = "${local.name_prefix}-reconciler"
  role   = aws_iam_role.reconciler.id
  policy = data.aws_iam_policy_document.reconciler.json
}

data "aws_iam_policy_document" "api_gateway_assume_role" {
  statement {
    sid     = "AllowApiGatewayServiceAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_gateway_logs" {
  name               = "${local.name_prefix}-api-logs"
  assume_role_policy = data.aws_iam_policy_document.api_gateway_assume_role.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "api_gateway_logs" {
  statement {
    sid    = "WriteApiAccessLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.api_access.arn}:*"]
  }
}

resource "aws_iam_role_policy" "api_gateway_logs" {
  name   = "${local.name_prefix}-api-logs"
  role   = aws_iam_role.api_gateway_logs.id
  policy = data.aws_iam_policy_document.api_gateway_logs.json
}

resource "aws_api_gateway_account" "this" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_logs.arn
}
