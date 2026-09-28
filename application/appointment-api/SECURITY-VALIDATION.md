# Appointment API Security Validation Boundary

This document records the security behaviors covered by the local Wave 3 test
suite and the behaviors that still require validation against an AWS deployment.
It contains no credentials, patient data, or deployment output.

## Signed-request transformation rules

The HMAC covers a canonical request constructed from the HTTP method, exact API
path, absence of a query string, content type, key identifier, timestamp, nonce,
idempotency key, and the SHA-256 digest of the exact decoded request-body bytes.

Consequently, any transformation that changes those decoded bytes intentionally
changes the digest and invalidates the original signature. This includes JSON
whitespace or property-order changes, LF/CRLF changes inside string values,
Unicode encoding changes, and changing an optional field between absent and
present. Base64 and non-base64 API Gateway events are equivalent only when they
decode to exactly the same body bytes. Header names are case-insensitive, but
duplicate security headers are rejected. Query strings are prohibited and the
route is fixed to `POST /appointments`.

Clients must therefore sign the final serialized byte sequence they transmit;
intermediaries must not reformat a signed body.

## Locally validated controls

The automated suite covers negative and adversarial authentication, replay and
idempotency behavior, schema and size rejection, privacy-safe responses and
logs, workflow state-transition ownership, stale-work reconciliation, bounded
retry/manual-review behavior, and static Terraform security invariants for API
Gateway, WAF, IAM, logging, queues, secrets metadata, and monitoring.

The tests use synthetic identifiers only. They do not prove that cloud resources
exist or that a deployed endpoint enforces the reviewed configuration.

## Deployment-only validation still required

The following controls cannot be proven by local unit, contract, or static
configuration tests and must be exercised after an explicitly approved apply:

- API Gateway and AWS WAF runtime handling of duplicate headers, managed rules,
  request-size rules, and rate limits.
- Actual Secrets Manager provisioning, access, rotation, and disabled-key
  behavior with the dedicated runtime identity.
- DynamoDB transaction and conditional-write behavior under real concurrency.
- SQS visibility timeout, redrive, DLQ retention, and EventBridge reconciliation
  timing under service failure.
- CloudWatch EMF ingestion, metric/alarm transitions, SNS topic-policy
  enforcement, and end-to-end delivery to a confirmed human subscription.
- Real clinical adapter behavior, because the current adapter is deliberately a
  non-success placeholder and cannot create a confirmed appointment.

Until those checks are complete, local readiness must not be represented as
deployment, live-control, or clinical-workflow validation.
