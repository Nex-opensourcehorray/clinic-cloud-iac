# W3.3 continues to use AWS-owned/service-managed encryption for DynamoDB, SQS,
# CloudWatch Logs, and the Secrets Manager secret metadata. A customer-managed
# Appointment API key is deferred until its policy, recovery ownership, cost,
# and service-principal access receive explicit review. No secret value is
# created or passed through this module.
