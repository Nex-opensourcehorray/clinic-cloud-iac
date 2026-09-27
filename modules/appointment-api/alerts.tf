data "aws_caller_identity" "appointment_api" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

resource "aws_sns_topic" "alerts" {
  name              = "clinic-nonprod-appointment-api-alerts"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(
    local.common_tags,
    {
      DataPurpose = "operational-alarm-routing"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_policy_document" "alert_topic" {
  statement {
    sid    = "AllowAccountOwnerAdministration"
    effect = "Allow"
    actions = [
      "sns:AddPermission",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:Publish",
      "sns:Receive",
      "sns:RemovePermission",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
    ]
    resources = [aws_sns_topic.alerts.arn]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.appointment_api.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowAppointmentApiCloudWatchAlarms"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.appointment_api.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.appointment_api.account_id}:alarm:${local.name_prefix}-*"
      ]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alert_topic.json
}
