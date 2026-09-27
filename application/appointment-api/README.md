# Appointment API authentication and workflow contract

W3.3 adds fail-closed HMAC authentication, durable replay protection, atomic
idempotency reservation, and a data-minimized SQS handoff. It does not include
a clinical-system adapter or claim exactly-once queue delivery.

## Signed request

`POST /appointments` accepts no query parameters and requires
`application/json` plus these six security headers:

- `X-Clinic-Key-Id`
- `X-Clinic-Timestamp` (Unix epoch seconds, maximum skew 300 seconds)
- `X-Clinic-Nonce` (retained for at least 600 seconds)
- `Idempotency-Key` (retained for seven days)
- `X-Content-SHA256` (lower- or uppercase hexadecimal SHA-256)
- `X-Clinic-Signature` (`v1=` followed by a base64 HMAC-SHA-256)

Names are matched case-insensitively. Duplicate or ambiguous security headers
are rejected. The digest and HMAC cover the exact decoded request bytes; the
body is not reserialized before verification. Base64 API Gateway bodies are
decoded before their digest is calculated.

The canonical request is UTF-8 with newline separators and this exact layout:

```text
CLINIC-HMAC-V1
POST
/appointments
<empty canonical-query line>
application/json
<lowercase body SHA-256>
<timestamp>
<nonce>
<idempotency key>
```

The public endpoint cannot reserve state or enqueue work unless authentication
succeeds. HMAC comparison uses a constant-time comparison.

## Secret key-ring document

Terraform creates only Secrets Manager metadata, using the AWS-managed Secrets
Manager encryption key. It never creates a secret version. A separate approved
out-of-band process must provision a document shaped like this, replacing the
placeholders with generated secret material:

```json
{
  "keys": {
    "v1": {
      "enabled": true,
      "key": "<current-secret-material-at-least-32-bytes>"
    },
    "v0": {
      "enabled": true,
      "key": "<previous-secret-material-at-least-32-bytes>"
    }
  }
}
```

Multiple enabled key IDs allow controlled overlap during rotation. Missing,
unreadable, malformed, unknown, disabled, or undersized key material fails
closed. Secrets and complete signatures are never logged.

## Durable workflow

The intake transaction conditionally creates three namespaces in the existing
workflow table:

- `NONCE#<key-id>#<nonce>`
- `IDEMPOTENCY#<key-id>#<idempotency-key>`
- `REQUEST#<request-id>`

The request begins in `QUEUE_PENDING`. SQS receives only the nonclinical request
and correlation identifiers. A successful handoff becomes `QUEUED`; a failed
send is marked `RECONCILE_REQUIRED` where possible. Because DynamoDB and SQS do
not share a transaction, an uncertain send remains recoverable state and is
never blindly re-sent by the intake invocation. SQS Standard remains
at-least-once, and a future clinical adapter must keep worker processing
idempotent. The current worker performs no clinical action.

## Data and logging boundary

The schema intentionally excludes diagnosis, treatment notes, prescriptions,
laboratory/radiology data, payment-card data, credentials, secrets, and free
text. Logs contain only approved operational categories and identifiers—not
request bodies, contact fields, secret values, or complete signatures.

## Public-edge boundary

The approved path is browser to the Vercel server, then Vercel to the Regional
API Gateway endpoint. Browsers are not intended to call API Gateway directly,
so the API intentionally publishes no CORS headers or preflight method. WAF
managed rules, a 16 KiB fail-closed body-size rule, a 300-request/five-minute
source-IP rate limit, and API throttling reduce abuse; they do not authenticate
Vercel or replace HMAC, replay protection, or idempotency.

Lambda responses and API Gateway-generated default errors use
`Cache-Control: no-store`. WAF logs redact query strings, every HMAC/idempotency
header, Authorization, and Cookie. API access and application logs contain
operational metadata only and never record request bodies.

The source-IP limit can affect clients sharing a NAT or proxy and cannot stop
distributed abuse. WAF logging currently retains allowed and blocked request
metadata; sampled-request display is disabled, while CloudWatch metrics remain
enabled for each rule.

## Build

Run `build.ps1` to create `dist/appointment-api.zip`. The generated directory
is ignored by Git and requires no live secret or dependency download.
