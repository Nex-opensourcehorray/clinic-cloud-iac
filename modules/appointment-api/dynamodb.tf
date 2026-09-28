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

  attribute {
    name = "reconcile_status"
    type = "S"
  }

  attribute {
    name = "next_attempt_at"
    type = "N"
  }

  global_secondary_index {
    name            = "reconciliation-index"
    hash_key        = "reconcile_status"
    range_key       = "next_attempt_at"
    projection_type = "KEYS_ONLY"
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
      DataPurpose = "nonce-idempotency-request-and-reconciliation-state"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}
