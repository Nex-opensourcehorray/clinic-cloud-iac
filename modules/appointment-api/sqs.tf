resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name_prefix}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = merge(
    local.common_tags,
    {
      QueuePurpose = "failed-appointment-work"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_sqs_queue" "work" {
  name                       = "${local.name_prefix}-work"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = var.queue_visibility_timeout_seconds
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })

  tags = merge(
    local.common_tags,
    {
      QueuePurpose = "appointment-work"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.work.arn]
  })
}

data "aws_iam_policy_document" "work_queue_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.work.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "work" {
  queue_url = aws_sqs_queue.work.id
  policy    = data.aws_iam_policy_document.work_queue_transport.json
}

data "aws_iam_policy_document" "dead_letter_queue_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.dead_letter.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id
  policy    = data.aws_iam_policy_document.dead_letter_queue_transport.json
}
