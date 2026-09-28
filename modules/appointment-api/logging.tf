resource "aws_cloudwatch_log_group" "intake" {
  name              = "/aws/lambda/${local.name_prefix}-intake"
  retention_in_days = var.log_retention_days

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.name_prefix}-worker"
  retention_in_days = var.log_retention_days

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "reconciler" {
  name              = "/aws/lambda/${local.name_prefix}-reconciler"
  retention_in_days = var.log_retention_days

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${local.name_prefix}-access"
  retention_in_days = var.log_retention_days

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}
