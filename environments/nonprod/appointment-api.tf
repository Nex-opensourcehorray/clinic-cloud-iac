module "appointment_api" {
  source = "../../modules/appointment-api"

  resource_name_prefix      = local.name_prefix
  environment               = var.environment
  hmac_secret_arn           = var.appointment_api_hmac_secret_arn
  intake_role_arn           = var.appointment_api_intake_role_arn
  worker_role_arn           = var.appointment_api_worker_role_arn
  reconciler_role_arn       = var.appointment_api_reconciler_role_arn
  api_gateway_logs_role_arn = var.appointment_api_api_gateway_logs_role_arn
  common_tags = merge(
    local.common_tags,
    {
      DataClassification = "internal"
      System             = "appointment-workflow"
    }
  )

  request_schema = jsondecode(
    file("${path.root}/../../application/appointment-api/schema/appointment-request.schema.json")
  )

  lambda_package_path = abspath(
    "${path.root}/../../application/appointment-api/dist/appointment-api.zip"
  )

  stage_name                      = "nonprod"
  idempotency_ttl_days            = 7
  log_retention_days              = 90
  api_throttle_rate_limit         = 10
  api_throttle_burst_limit        = 20
  waf_rate_limit                  = 300
  maximum_request_body_bytes      = 16384
  maximum_clock_skew_seconds      = 300
  nonce_ttl_seconds               = 600
  processing_lease_seconds        = 120
  reconciliation_stale_seconds    = 300
  reconciliation_backoff_seconds  = 300
  maximum_reconciliation_attempts = 3
  reconciliation_batch_size       = 25
}
