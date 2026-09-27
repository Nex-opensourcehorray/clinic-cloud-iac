resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${local.name_prefix}-operations"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          title  = "API requests, server errors, and latency"
          region = data.aws_region.current.region
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", aws_api_gateway_rest_api.this.name, "Stage", aws_api_gateway_stage.this.stage_name, { stat = "SampleCount" }],
            [".", "5XXError", ".", ".", ".", ".", { stat = "Sum" }],
            [".", "Latency", ".", ".", ".", ".", { stat = "Average", yAxis = "right" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type = "metric"
        properties = {
          title  = "Lambda errors, throttles, and duration"
          region = data.aws_region.current.region
          period = 300
          metrics = concat(
            [for name in values(local.monitored_lambda_functions) : ["AWS/Lambda", "Errors", "FunctionName", name, { stat = "Sum" }]],
            [for name in values(local.monitored_lambda_functions) : ["AWS/Lambda", "Throttles", "FunctionName", name, { stat = "Sum" }]],
            [for name in values(local.monitored_lambda_functions) : ["AWS/Lambda", "Duration", "FunctionName", name, { stat = "Average", yAxis = "right" }]]
          )
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type = "metric"
        properties = {
          title  = "Work queue and dead-letter queue"
          region = data.aws_region.current.region
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.work.name, { stat = "Maximum" }],
            [".", "ApproximateAgeOfOldestMessage", ".", ".", { stat = "Maximum", yAxis = "right" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.dead_letter.name, { stat = "Maximum" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type = "metric"
        properties = {
          title  = "DynamoDB operational health"
          region = data.aws_region.current.region
          period = 300
          metrics = concat(
            [for operation in ["GetItem", "UpdateItem", "TransactWriteItems", "Query"] : ["AWS/DynamoDB", "SystemErrors", "TableName", aws_dynamodb_table.workflow.name, "Operation", operation, { stat = "Sum" }]],
            [
              ["AWS/DynamoDB", "ReadThrottleEvents", "TableName", aws_dynamodb_table.workflow.name, { stat = "Sum" }],
              [".", "WriteThrottleEvents", ".", ".", { stat = "Sum" }],
            ]
          )
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type = "metric"
        properties = {
          title  = "Workflow reconciliation and exception signals"
          region = data.aws_region.current.region
          period = 300
          metrics = [
            ["Clinic/AppointmentApi", "StaleQueueState", { stat = "Sum" }],
            [".", "ReconciliationFailure", { stat = "Sum" }],
            [".", "ManualReviewBacklog", { stat = "Sum" }],
            [".", "ProcessingLeaseExpired", { stat = "Sum" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
    ]
  })
}
