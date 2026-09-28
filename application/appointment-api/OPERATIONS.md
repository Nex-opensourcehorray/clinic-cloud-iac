# Appointment API Operational Alert Runbook

## Routing boundary

All 14 Appointment API alarms route alarm and recovery state changes to the
encrypted `clinic-nonprod-appointment-api-alerts` SNS topic. The topic accepts
publish requests only from same-account, same-Region CloudWatch alarms whose
names start with the Appointment API resource prefix. Lambda functions have no
SNS publish permission.

No subscription is configured. The topic is a technical routing target, not a
confirmed human-notification path. An owner-approved destination must be added
before operational acceptance. Do not invent an email address, phone number,
chat channel, webhook, or incident-management integration.

Alarm and recovery notifications contain CloudWatch operational alarm metadata
only. Metrics, dashboard widgets, and notifications must not contain request
bodies, patient/contact values, clinical details, HMAC material, credentials,
tokens, signatures, or DynamoDB item payloads.

## Alarm inventory and severity

SEV-1 / Critical is reserved for a confirmed or sustained inability to accept
or process appointment requests. No single current alarm automatically proves
that condition; operators escalate to SEV-1 only after correlating multiple
signals or confirming an outage.

| Alarm suffix | Signal | Severity |
|---|---|---|
| `intake-errors` | Intake Lambda errors | SEV-3 / Operational |
| `worker-errors` | Worker Lambda errors | SEV-3 / Operational |
| `reconciler-errors` | Reconciler Lambda errors | SEV-3 / Operational |
| `intake-throttles` | Intake Lambda throttles | SEV-3 / Operational |
| `worker-throttles` | Worker Lambda throttles | SEV-3 / Operational |
| `reconciler-throttles` | Reconciler Lambda throttles | SEV-3 / Operational |
| `api-5xx` | API Gateway server errors | SEV-2 / High |
| `work-queue-age` | Oldest work message over five minutes | SEV-2 / High |
| `dlq-messages` | DLQ has visible messages | SEV-2 / High |
| `dynamodb-system-errors` | Workflow-table system errors | SEV-2 / High |
| `stale-queue-state` | Stale queue or processing state | SEV-3 / Operational |
| `reconciliation-failure` | Reconciliation failed or remained uncertain | SEV-2 / High |
| `manual-review-backlog` | Manual-review work exists | SEV-2 / High |
| `processing-lease-expired` | Processing ownership lease expired | SEV-3 / Operational |

## First response

1. Acknowledge the alarm through the approved incident process once a human
   destination exists; do not acknowledge by mutating application state.
2. Confirm the alarm time, state transition, metric, dimensions, and affected
   AWS resource on the Appointment API operations dashboard.
3. Correlate API, Lambda, SQS, DynamoDB, and workflow metrics. Inspect only
   data-minimized logs and safe request/correlation references.
4. Inspect the authoritative DynamoDB request status before any recovery step.
5. Escalate severity only when impact is confirmed; an isolated error or
   throttle is not automatically a clinical outage.
6. Treat the SNS `OK` notification as evidence that the metric recovered, not
   proof that every affected workflow item was reconciled.

## Queue, reconciliation, and exception handling

- **DLQ:** Inspect the safe message reference and authoritative DynamoDB state.
  Never automatically delete or redrive DLQ messages. Manual redrive requires
  separate operational approval.
- **Stale queue state:** Verify queue availability and the request's status,
  lease, and next-attempt timestamp. Allow bounded reconciliation to operate;
  do not bypass conditional ownership.
- **Reconciliation failure:** Check retry count, backoff, ownership, and SQS
  availability. Repeated uncertainty must move to manual review rather than
  infinite redrive.
- **Manual-review backlog:** Assign an approved operator, inspect authoritative
  status, and follow the future clinical integration procedure. Never infer
  clinical success from transport success.
- **Processing lease expiry:** Confirm the lease is expired and rely on the
  conditional acquisition path. Do not manually overwrite an active owner.

Recovery notifications are enabled for all alarms because they close the
operational state-change loop. Operators must still verify authoritative
DynamoDB state, remaining queue/DLQ depth, and related alarms before closure.
