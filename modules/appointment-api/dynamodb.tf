resource "aws_dynamodb_table" "workflow" {
  name         = "${local.name_prefix}-workflow"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = merge(
    local.common_tags,
    {
      DataPurpose = "nonce-idempotency-request-state"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}
