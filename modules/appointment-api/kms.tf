# W3.2 intentionally uses AWS-owned/service-managed encryption for DynamoDB,
# SQS, and CloudWatch Logs. A customer-managed Appointment API key is deferred
# until its key policy, recovery ownership, cost, and service-principal access
# have received explicit review. No secret value is created or passed through
# this module.
