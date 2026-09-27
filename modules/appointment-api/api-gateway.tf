resource "aws_api_gateway_rest_api" "this" {
  name        = local.name_prefix
  description = "Nonproduction public boundary for the controlled Appointment API workflow"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = local.common_tags
}

resource "aws_api_gateway_resource" "appointments" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "appointments"
}

resource "aws_api_gateway_model" "appointment_request" {
  rest_api_id  = aws_api_gateway_rest_api.this.id
  name         = "AppointmentRequest"
  description  = "Data-minimized nonproduction appointment request"
  content_type = "application/json"
  schema       = jsonencode(var.request_schema)
}

resource "aws_api_gateway_request_validator" "appointment_request" {
  rest_api_id                 = aws_api_gateway_rest_api.this.id
  name                        = "validate-appointment-request"
  validate_request_body       = true
  validate_request_parameters = true
}

resource "aws_api_gateway_method" "post_appointments" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.appointments.id
  http_method   = "POST"
  authorization = "NONE"

  request_validator_id = aws_api_gateway_request_validator.appointment_request.id

  request_models = {
    "application/json" = aws_api_gateway_model.appointment_request.name
  }

  request_parameters = {
    "method.request.header.Content-Type"       = true
    "method.request.header.Idempotency-Key"    = true
    "method.request.header.X-Clinic-Key-Id"    = true
    "method.request.header.X-Clinic-Nonce"     = true
    "method.request.header.X-Clinic-Signature" = true
    "method.request.header.X-Clinic-Timestamp" = true
    "method.request.header.X-Content-SHA256"   = true
  }
}

resource "aws_api_gateway_integration" "intake" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = aws_api_gateway_resource.appointments.id
  http_method = aws_api_gateway_method.post_appointments.http_method

  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.intake.invoke_arn
  timeout_milliseconds    = 9000
}

resource "aws_lambda_permission" "api_gateway_intake" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.intake.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/${var.stage_name}/POST/appointments"
}

resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_4XX"

  response_templates = {
    "application/json" = jsonencode({
      message   = "Request rejected"
      requestId = "$context.requestId"
    })
  }

  response_parameters = {
    "gatewayresponse.header.Cache-Control" = "'no-store'"
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_5XX"

  response_templates = {
    "application/json" = jsonencode({
      message   = "Request could not be processed"
      requestId = "$context.requestId"
    })
  }

  response_parameters = {
    "gatewayresponse.header.Cache-Control" = "'no-store'"
  }
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode({
      resource_id          = aws_api_gateway_resource.appointments.id
      method_id            = aws_api_gateway_method.post_appointments.id
      request_parameters   = aws_api_gateway_method.post_appointments.request_parameters
      integration_uri      = aws_api_gateway_integration.intake.uri
      request_model_schema = aws_api_gateway_model.appointment_request.schema
      response_4xx         = aws_api_gateway_gateway_response.default_4xx.response_templates
      response_4xx_headers = aws_api_gateway_gateway_response.default_4xx.response_parameters
      response_5xx         = aws_api_gateway_gateway_response.default_5xx.response_templates
      response_5xx_headers = aws_api_gateway_gateway_response.default_5xx.response_parameters
    }))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.intake,
    aws_api_gateway_gateway_response.default_4xx,
    aws_api_gateway_gateway_response.default_5xx,
  ]
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id          = aws_api_gateway_rest_api.this.id
  deployment_id        = aws_api_gateway_deployment.this.id
  stage_name           = var.stage_name
  xray_tracing_enabled = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      extendedRequestId  = "$context.extendedRequestId"
      requestTimeEpoch   = "$context.requestTimeEpoch"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      responseLength     = "$context.responseLength"
      integrationStatus  = "$context.integrationStatus"
      integrationLatency = "$context.integrationLatency"
    })
  }

  tags = local.common_tags

  depends_on = [aws_api_gateway_account.this]
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    data_trace_enabled     = false
    logging_level          = "OFF"
    throttling_rate_limit  = var.api_throttle_rate_limit
    throttling_burst_limit = var.api_throttle_burst_limit
  }
}
