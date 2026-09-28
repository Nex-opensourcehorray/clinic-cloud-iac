# Appointment API authentication and workflow contract

> **Wave 3 status:** ENGINEERING CLOSED — DEPLOYMENT DEFERRED. Thirty Wave 3
> Terraform-managed resources exist. The reviewed final 21-resource non-IAM
> remainder was not deployed. This design is not operationally accepted,
> production ready, or clinically integrated.

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

The Secrets Manager container is an **externally managed operational
dependency**. Its ARN is supplied to Terraform as a non-sensitive identifier so
Terraform can configure the intake Lambda and scope its
`secretsmanager:GetSecretValue` permission. Terraform does not create, import,
delete, or read the secret resource or any secret version.

This ownership boundary is a documented W3.8 recovery architecture decision.
AWS provider v6.65.0 repeatedly stalled during both create and refresh of the
Secrets Manager resource. Secret metadata and value lifecycle therefore remain
outside Terraform for this deployment. A future provider remediation may allow
the ownership decision to be reconsidered, but not during the current recovery.

A separate approved out-of-band process must provision a document shaped like
this, replacing the placeholders with generated secret material:

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
closed. The HMAC value remains outside Terraform, state, Git, logs, and evidence.
Secrets, secret ARNs, and complete signatures are never logged.

## Externally managed IAM prerequisites

Terraform consumes the following exact nonproduction role ARNs as required
inputs. It does not create, read, update, delete, or otherwise manage these
roles, their trust policies, inline or managed policies, permissions
boundaries, or lifecycle:

| Purpose | Exact role ARN | Required trust | Reviewed permission contract | Expected boundary |
|---|---|---|---|---|
| Intake | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/clinic-nonprod-appointment-api-intake` | `lambda.amazonaws.com` | Workflow-table `GetItem`/`TransactWriteItems`, work-queue `SendMessage`, exact HMAC-secret `GetSecretValue`, own log-stream writes, and X-Ray telemetry writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| Worker | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/clinic-nonprod-appointment-api-worker` | `lambda.amazonaws.com` | Workflow-table `GetItem`/`UpdateItem`, work-queue receive/delete/visibility/attribute access, own log-stream writes, and X-Ray telemetry writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| Reconciler | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/clinic-nonprod-appointment-api-reconciler` | `lambda.amazonaws.com` | Workflow-table `GetItem`/`UpdateItem`, reconciliation-index `Query`, work-queue `SendMessage`, own log-stream writes, and X-Ray telemetry writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| API logging | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/clinic-nonprod-appointment-api-api-logs` | `apigateway.amazonaws.com` | Logging-only `CreateLogStream`, `DescribeLogStreams`, and `PutLogEvents` beneath the Appointment API access log group | `clinic-nonprod-appointment-api-api-logs-boundary` |

The IAM owner is responsible for proving role existence and maintaining the
reviewed trust, policy, and boundary configuration. These checks are required
before apply and must be performed outside Terraform when the deployment
identity cannot read IAM.

The Terraform deployment identity requires narrowly scoped `iam:PassRole` for
each exact role. The three Lambda roles must be restricted with
`iam:PassedToService = lambda.amazonaws.com`; where authorization support is
reliable, each must also retain the reviewed exact
`iam:AssociatedResourceArn` pairing with its matching Lambda function. The API
logging role must be restricted with
`iam:PassedToService = apigateway.amazonaws.com`. Broad `iam:*`, unrestricted
`iam:PassRole`, AdministratorAccess, and PowerUserAccess workarounds are not
approved.

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

HTTP `202 Accepted` is an API response semantic, not a persisted workflow
state. The intake transaction writes `QUEUE_PENDING` atomically; adding an
intermediate `ACCEPTED` write would introduce another failure window.

## W3.5 state and ownership model

The request record is the authoritative workflow state. Legal business-state
transitions are:

| Current state | Legal next states |
|---|---|
| `QUEUE_PENDING` | `QUEUED`, `PROCESSING`, `RECONCILE_REQUIRED`, `MANUAL_REVIEW_REQUIRED` |
| `QUEUED` | `PROCESSING`, `RECONCILE_REQUIRED`, `MANUAL_REVIEW_REQUIRED` |
| `PROCESSING` | `FAILED_RETRYABLE`, `RECONCILE_REQUIRED`, `MANUAL_REVIEW_REQUIRED`, reserved future `SUCCEEDED` |
| `FAILED_RETRYABLE` | `QUEUED`, `PROCESSING`, `RECONCILE_REQUIRED`, `MANUAL_REVIEW_REQUIRED` |
| `RECONCILE_REQUIRED` | `QUEUED`, `PROCESSING`, `MANUAL_REVIEW_REQUIRED` |
| `MANUAL_REVIEW_REQUIRED` | Terminal pending operator action |
| `SUCCEEDED` | Terminal and reserved for a future approved clinical adapter |

Application validation rejects invalid transitions before an update, while
DynamoDB conditions remain authoritative against concurrent workers. Acquiring
or renewing ownership without changing status is metadata mutation, not a
business-state self-transition.

Before any future clinical side effect, a worker conditionally changes an
eligible request to `PROCESSING`, records an opaque owner token, increments the
processing attempt, and sets a 120-second nonproduction lease. A fresh owner
blocks duplicate delivery. An expired lease can be acquired atomically by one
replacement worker. Ownership is never held only in Lambda memory.

No approved clinical adapter exists. The foundation adapter returns
`UNKNOWN_RESULT`; unknown, nonretryable, and even unexpected `SUCCESS` results
are escalated to `MANUAL_REVIEW_REQUIRED`. W3.5 never writes `SUCCEEDED` and
never reports a clinically confirmed appointment.

## Reconciliation and manual review

Only request records carry `reconcile_status` and `next_attempt_at`. The
`reconciliation-index` GSI uses those fields as partition and sort keys with a
`KEYS_ONLY` projection. The reconciler uses bounded `Query` operations, never a
table scan, with a nonproduction limit of 25 records per eligible state.

`QUEUE_PENDING` becomes eligible after the configurable 300-second stale
threshold. `RECONCILE_REQUIRED`, `FAILED_RETRYABLE`, and expired `PROCESSING`
records are also queryable. Reconciliation conditionally acquires an ownership
lease, increments its attempt counter, and sends only request/correlation
references. A confirmed send changes the request to `QUEUED`; an uncertain
send remains recoverable with a 300-second backoff. After three attempts, the
request becomes `MANUAL_REVIEW_REQUIRED`. These values are project defaults,
not universal operating requirements.

Manual-review state contains only safe operational identifiers, timestamps,
counters, ownership metadata, and an exception category. It does not duplicate
appointment, contact, clinical, authentication, or credential data. Durable
DynamoDB state plus alarms is simpler than adding an exception queue for this
foundation.

## DLQ procedure

The encrypted SQS DLQ is transport-failure evidence and diagnostic input; it
is not authoritative workflow state. The nonproduction procedure is:

1. The DLQ alarm fires; notification routing must be approved before operational acceptance.
2. An operator inspects only the safe request/correlation reference.
3. The operator checks the authoritative DynamoDB request state.
4. Automated bounded reconciliation remains authoritative where eligible.
5. Exhausted recovery becomes `MANUAL_REVIEW_REQUIRED`.
6. DLQ messages are not automatically deleted or redriven.
7. Any manual redrive requires separate operational approval.

SQS Standard remains at-least-once. Duplicate transport messages are expected
and are absorbed by conditional worker ownership; exactly-once delivery is not
claimed.

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
