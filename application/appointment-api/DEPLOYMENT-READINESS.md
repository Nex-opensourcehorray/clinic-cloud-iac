# W3.8 Deployment Readiness and Live Validation Gate

This document records the deployment-deferred closeout of the controlled
nonproduction Appointment API. Thirty Wave 3 Terraform-managed resources are
deployed. The reviewed remaining 21 non-IAM resources are not deployed. The
externally managed HMAC Secrets Manager container exists with zero versions; no
HMAC value, SNS subscription, or live authentication test exists.

Wave 3 is **ENGINEERING CLOSED — DEPLOYMENT DEFERRED**. The reviewed
`wave3-recovery4.tfplan` had 21 additions, zero changes, zero destroys, and zero
replacements with SHA-256
`761BD9223205D4688BDB04E11444B48902C1279C0E731FA6CFEA08368B37BC04`; it was
deleted at closeout and is not authorized for reuse. No current deployment
plan or apply authorization exists.

## Planned deployment inventory

| Group | Count | Planned resources and scope |
|---|---:|---|
| API Gateway | 11 | Regional REST API, `/appointments` resource, request model and validator, one POST method and integration, default 4xx/5xx responses, deployment, stage, and method settings |
| WAF | 3 | Regional web ACL, stage association, and WAF logging configuration |
| Lambda | 3 | Intake, worker, and reconciler functions |
| Lambda and event integrations | 5 | API Gateway Lambda permission, SQS event source mapping, EventBridge rule and target, and EventBridge Lambda permission |
| IAM | 0 | Four roles, their policies, trust, boundaries, and lifecycle are externally managed prerequisites |
| DynamoDB | 1 | Encrypted, point-in-time-recoverable workflow table with TTL and reconciliation index |
| SQS and DLQ | 5 | Work queue, DLQ, redrive allow policy, and two transport policies |
| CloudWatch logs | 5 | Intake, worker, reconciler, API access, and WAF log groups |
| CloudWatch alarms | 14 | Lambda, API, queue, DLQ, DynamoDB, and workflow operational alarms |
| SNS | 2 | Encrypted alert topic and scoped topic policy; no subscription |
| CloudWatch dashboard | 1 | Appointment API operations dashboard |
| Secrets Manager | 0 | HMAC container is an externally managed operational dependency, not a Terraform resource or data lookup |
| API Gateway account configuration | 1 | Regional/account-wide CloudWatch logging role association |
| **Terraform-managed target** | **51** | **External secret and IAM prerequisites excluded; 30 currently deployed and 21 expected to remain, subject to the authoritative recovery plan** |

### Special scope and dependencies

- The Regional API Gateway stage is a public endpoint protected by AWS WAF,
  request validation, throttling, exact request targeting, and Lambda HMAC
  authentication. No Lambda function is directly public.
- `aws_api_gateway_account.this` is account/region-wide API Gateway logging
  configuration. The previously inspected `cloudwatchRoleArn` was empty. A
  future apply will set it to the externally managed API Gateway logging role, and the
  owner must acknowledge that regional/account-wide effect explicitly.
- API Gateway and EventBridge invocation permissions are source-ARN scoped.
  The SNS topic policy is source-account and alarm-ARN scoped. SQS policies
  provide explicit insecure-transport Deny statements.
- Operational dependencies are the Lambda ZIP, workflow table, work queue and
  DLQ, EventBridge reconciliation rule, CloudWatch logs/metrics/alarms, alert
  topic, externally managed HMAC container and key-ring value, and later an
  approved human alert destination.
- `prevent_destroy` protects the DynamoDB table, SNS topic, both queues, and all
  five Wave 3 log groups. These nine resources need
  explicit lifecycle review before any rollback that would remove them.
- The API Gateway deployment uses `create_before_destroy`; this is deployment
  replacement safety, not authorization to apply or destroy.

## Pre-apply dependency classification

| Dependency | Classification | Gate or rationale |
|---|---|---|
| Terraform formatting and validation | READY | Current configuration passes `fmt -check` and `validate` |
| Lambda build artifact | READY | Reproducible 14-file runtime ZIP; current reviewed SHA-256 is recorded in W3.7 evidence |
| External IAM roles and boundaries | REQUIRED BEFORE APPLY | IAM owner must confirm four exact roles, trusts, reviewed policies and boundaries; Terraform performs no IAM role lookup or lifecycle management |
| WAF and API design | READY | Regional, single POST route, WAF association, size/rate/managed-rule protections, and minimized logs passed review |
| DynamoDB and SQS workflow | READY | Conditional ownership, replay/idempotency, bounded reconciliation, encryption, PITR, and DLQ design passed tests |
| Planned encrypted SNS topic and scoped policy | READY | Topic and policy remain in the planned non-IAM deployment scope |
| Account-wide API Gateway logging role setting | REQUIRED BEFORE APPLY | Reconfirm `cloudwatchRoleArn` remains empty or matches the reviewed intent; owner must approve the regional/account-wide change |
| Fresh plan and package hash | DEPLOYMENT DEFERRED | The reviewed plan was deleted and cannot be reused; any future resumption requires a new plan and governance decision |
| Explicit project-owner approval | DEPLOYMENT DEFERRED | No apply is currently requested or authorized |
| HMAC Secrets Manager metadata | EXTERNAL DEPENDENCY | Existing empty container is managed outside Terraform; its ARN is supplied only for Lambda and exact IAM scope |
| HMAC secret value | REQUIRED AFTER APPLY BEFORE LIVE AUTH TEST | Must be provisioned out of band using synthetic nonproduction material |
| Human SNS subscription/destination | REQUIRED BEFORE OPERATIONAL ACCEPTANCE | Not required for initial foundation deployment; must be approved and tested before acceptance |
| Live monitoring and alert transitions | REQUIRED BEFORE OPERATIONAL ACCEPTANCE | Configuration is validated, but runtime transitions and delivery are not |
| Live API/WAF/DynamoDB/SQS validation | REQUIRED BEFORE OPERATIONAL ACCEPTANCE | Requires the deployed nonproduction environment |
| Real clinical adapter | DEFERRED TO LATER WAVE | Not required for foundation deployment; current adapter deliberately cannot claim success |
| Clinical-system connectivity | DEFERRED TO LATER WAVE | No current direct RDS, FSx, Directory Service, or clinical-system dependency |

## Externally managed IAM security contract

The following are externally managed IAM prerequisites. Terraform accepts only
their ARNs and does not create, read, update, delete, import, or otherwise own
their trust, policy, permissions-boundary, or lifecycle configuration.

| Role | Required trust | Reviewed runtime scope | Expected boundary |
|---|---|---|---|
| `arn:aws:iam::119033255630:role/clinic-nonprod-appointment-api-intake` | `lambda.amazonaws.com` | Exact workflow-table reservation, work-queue send, HMAC-secret read, own logs, and X-Ray writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| `arn:aws:iam::119033255630:role/clinic-nonprod-appointment-api-worker` | `lambda.amazonaws.com` | Exact workflow-table processing, work-queue consumption, own logs, and X-Ray writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| `arn:aws:iam::119033255630:role/clinic-nonprod-appointment-api-reconciler` | `lambda.amazonaws.com` | Exact workflow-table and reconciliation-index access, work-queue send, own logs, and X-Ray writes | `clinic-nonprod-appointment-api-runtime-boundary` |
| `arn:aws:iam::119033255630:role/clinic-nonprod-appointment-api-api-logs` | `apigateway.amazonaws.com` | Appointment API access-log stream creation, description, and writes only | `clinic-nonprod-appointment-api-api-logs-boundary` |

Before apply, the IAM owner must confirm all four roles exist and match this
contract. The deployment identity must have exact-resource `iam:PassRole` with
`iam:PassedToService = lambda.amazonaws.com` for each Lambda role and
`iam:PassedToService = apigateway.amazonaws.com` for the logging role. Where
reliably supported, the Lambda grants also retain exact matching
`iam:AssociatedResourceArn` conditions. No broad AdministratorAccess,
PowerUserAccess, `iam:*`, or unrestricted PassRole workaround is approved.

## HMAC key-ring provisioning gate

The externally managed container is exactly:

`clinic-nonprod-appointment-api/hmac-keys`

Terraform receives its ARN as `appointment_api_hmac_secret_arn`. Terraform does
not create, import, delete, or read the secret or its versions. This is the W3.8
recovery decision after repeated AWS provider v6.65.0 create and refresh stalls.
The metadata and value lifecycle remain out of band, and the value must never be
placed in Terraform, state, Git, logs, or evidence. Provider remediation may
justify a future ownership review, but ownership will not change during this
deployment.

The required document shape is:

```json
{
  "keys": {
    "v1": {
      "enabled": true,
      "key": "<current-synthetic-nonproduction-material-at-least-32-bytes>"
    },
    "v0": {
      "enabled": true,
      "key": "<previous-synthetic-nonproduction-material-at-least-32-bytes>"
    }
  }
}
```

Key identifiers must be 1–64 characters from letters, digits, `.`, `_`, or
`-`. Every key value must be at least 32 UTF-8 bytes. These placeholders are
structural examples only and are not usable secret values.

### Safest practical operator method

1. After deployment, use an explicitly approved, least-privilege, MFA-backed
   operator session in AWS Secrets Manager for `ap-east-1`.
2. Navigate directly to the exact secret name above and verify its metadata,
   tags, account, and region before editing.
3. Use the Secrets Manager console value editor and an approved password/secret
   generator to enter the JSON directly. Do not place the value in a command,
   PowerShell history, Terraform variable, local file, repository, evidence,
   ticket, chat, log, or clipboard manager.
4. Save one new secret version. Do not change the reviewed external metadata.
5. Clear any transient clipboard content, close the privileged session, and
   record only the secret name, version identifier, operator approval, time,
   and success/failure—not the value or complete signature.
6. Verify metadata with a read-only description call and validate behavior with
   synthetic signed requests. Do not print `get-secret-value` output.

If console entry cannot meet the operator's security requirements, stop and
design an approved secret-injection mechanism that accepts protected standard
input without exposing the value in arguments or files. Do not fall back to a
literal CLI argument.

### Rotation test

1. Add a new enabled key ID while leaving the previous key enabled.
2. Confirm synthetic requests signed by both current and previous IDs work
   during the overlap, each with a new nonce and timestamp.
3. Switch the synthetic client to the new ID and allow the five-minute timestamp
   window and in-flight retries to drain.
4. Change the previous key to `enabled: false`; verify the new key succeeds and
   the previous ID fails closed without revealing whether it was known.
5. Remove old material only after the rollback window and explicit approval.
   Record test results and version IDs only, never key material or signatures.

## Human alert destination gate

The plan creates the encrypted SNS alert topic with zero subscriptions. After
deployment, the owner must separately approve one controlled destination, such
as an operations email distribution, incident-management integration, or an
approved Chatbot/Slack integration. No address, channel, or integration is
assumed here.

This destination is **REQUIRED BEFORE OPERATIONAL ACCEPTANCE**, but it is not a
prerequisite for the initial nonproduction foundation apply. Technical SNS
publication can be tested before then; human delivery cannot be claimed until a
subscription is approved, confirmed, and exercised.

## Apply scope and blast radius

A future approved apply is expected to:

- create the remaining 21 non-IAM Wave 3 resources, subject to the authoritative fresh plan;
- update zero existing resources;
- destroy zero resources;
- replace zero resources; and
- leave Wave 0–2 VPC, subnet, route, endpoint, security-group, Directory
  Service, FSx, IAM, backup, and historical-log resources untouched.

The owner must explicitly acknowledge that the planned
`aws_api_gateway_account` creation sets the regional/account-wide API Gateway
CloudWatch logging role. The last read-only inspection found the existing value
empty. Any nonempty or unexpected value at the final check is a NO-GO.

The public blast radius is the new Regional API endpoint. Its only processing
route is `POST /appointments`; WAF, throttling, schema validation, exact-target
checks, and HMAC remain layered controls. There is no VPC attachment, Lambda
security group, NAT gateway, new VPC endpoint, RDS integration, FSx integration,
or Directory Service integration.

## Controlled future resumption procedure

Deployment is intentionally deferred. Do not perform these steps unless the
owner first reopens Wave 3 deployment through a new governance decision.

1. Confirm branch, approved HEAD, clean status, remote synchronization, operator
   identity, account, region, and the account-wide API Gateway logging setting.
2. Re-run `terraform fmt -check -recursive`, Terraform validation, all
   Appointment API tests, sensitive-file scans, and the Lambda build.
3. Verify the fresh ZIP contains exactly 14 runtime files and record its hash.
4. With the approved profile and region set only for the command, create a
   local ignored plan file:

   ```powershell
   terraform -chdir=environments/nonprod plan -input=false -detailed-exitcode -out=<new-reviewed-plan>.tfplan
   ```

5. Require exit code 2 and the reviewed non-IAM additions, zero changes, zero destroys,
   and zero replacements. Inspect the complete plan with `terraform show` and
   record the local plan hash. Never commit or publish the binary plan.
6. Stop on any unexpected address or existing-resource action. Obtain explicit
   project-owner approval tied to the reviewed plan hash and blast radius.
7. Only after that approval, the exact command requiring approval is:

   ```powershell
   terraform -chdir=environments/nonprod apply -input=false <new-reviewed-plan>.tfplan
   ```

8. Capture sanitized apply output and exact resource counts without state,
   credentials, endpoints containing secrets, or request data.
9. Immediately inventory resources, re-run a read-only plan, and begin the
   pre-secret smoke matrix. Stop on partial creation or drift.
10. Retain the local plan only as long as required by the approved procedure,
    then remove it according to local sensitive-artifact handling.

## Pre-secret post-apply smoke matrix

These tests may run before any secret value exists. All requests use synthetic
data, and no appointment action is expected.

| Test | Expected result |
|---|---|
| Resource inventory | All 51 Terraform-managed Wave 3 resources and four external IAM roles exist; no Wave 0–2 change |
| API and WAF attachment | Regional endpoint and exactly one stage association exist |
| Unauthenticated POST | Generic rejection; no workflow-table item and no SQS message |
| Syntactically complete request with missing secret value | Fail closed with a generic temporary-authentication failure; no business side effect |
| Unsupported method/path/query | Rejected; no alternate integration |
| Logging review | Only allowlisted request/correlation and operational metadata; no body, signature, digest, nonce, or contact values |
| Monitoring inventory | Fourteen alarms, dashboard, encrypted SNS topic, and zero subscriptions exist |
| Initial queue/table state | No unexpected queue messages, DLQ messages, or workflow records |

## Post-secret live authentication matrix

Provisioning the secret needs separate approval. Use synthetic appointment
identifiers only and record sanitized results.

| Test | Expected result |
|---|---|
| Valid signed request | HTTP 202 acceptance, one logical workflow reservation, reference-only queue message; no clinical confirmation |
| Bad HMAC | Generic authentication rejection and no business side effect |
| Timestamp older than 300 seconds | Fail closed |
| Timestamp more than 300 seconds in the future | Fail closed |
| Reused nonce | Conflict/replay rejection with no duplicate ownership |
| Same idempotency key/body with new nonce and signature | Existing request returned; no duplicate logical work |
| Same idempotency key with different digest | Conflict and no second request |
| Body larger than 16 KiB | WAF or application rejection before business processing |
| Wrong content type or unexpected query | Rejected before reservation |
| Malformed JSON or prohibited field | Generic contract rejection |
| Response privacy | No secret, topology, account, condition, or exception leakage |
| Log privacy | No body, clinical/contact value, signature, digest, nonce, token, or raw AWS item/message |

Because the adapter is intentionally unavailable, accepted work must ultimately
reach safe manual review; it must not persist `SUCCEEDED` or claim appointment
confirmation.

## Controlled live concurrency matrix

Do not run these tests until infrastructure and the HMAC value are approved.
Use isolated synthetic identifiers and cap concurrency.

| Scenario | Expected authoritative DynamoDB end state |
|---|---|
| Two simultaneous requests with the same nonce | One nonce owner and at most one request; loser is rejected as replay |
| Simultaneous same idempotency key and identical body with distinct nonces | One idempotency record linked to one request; retry observes the authoritative request |
| Simultaneous same idempotency key with different digests | One content owner; conflicting content is rejected and creates no second request |
| Duplicate SQS delivery | One processing owner; duplicate makes no adapter call and cannot regress state |
| Competing worker lease acquisition | Active lease and owner remain authoritative; loser performs no completion write |
| Stale intake queue confirmation | Newer worker/manual-review state remains unchanged |
| Competing reconciliation acquisition | One reconciliation owner and one bounded attempt increment; loser records no completion |

After each case, inspect only sanitized keys, state, ownership timestamps, and
attempt counters. Do not capture request bodies or authentication material.

## SQS and DLQ live-test plan

1. Submit one approved synthetic signed request and confirm the work-queue body
   contains only `requestId` and `correlationId` references.
2. Confirm normal worker delivery and authoritative DynamoDB transition. With
   the unavailable adapter, the safe result is manual review, not success.
3. Under separate mutation approval, submit one reference-only malformed test
   envelope that makes the worker return a batch failure. Observe bounded
   retries and the configured `maxReceiveCount` of five.
4. Confirm the message reaches the DLQ, queue depth remains bounded, and the DLQ
   alarm transitions. Use one message only; do not delete it automatically.
5. Exercise the work-queue age alarm only with a controlled single-message test
   and stop if processing or cost differs from expectation.
6. Inspect the DLQ message and authoritative workflow state using sanitized
   references. A manual redrive needs its own approval, a reviewed destination,
   and a pre/post state check. Never automatically delete or infinitely redrive.

## WAF live-test plan

Use a single synthetic client and stop at the first unexpected side effect.

- Send one body over 16 KiB and confirm WAF/application rejection and no
  workflow record.
- Send one harmless synthetic known-bad-input pattern and confirm the managed
  rule blocks it without logging sensitive content.
- Exercise the 300-requests-per-five-minute rate rule with a separately
  approved, bounded run capped just above the threshold, low concurrency, and
  immediate stop after the first rate block. This is not a load or denial-of-
  service test.
- Send one unsupported method/path and one unexpected query; confirm rejection
  and no alternate processing integration.
- Review WAF logs for header/query redaction and disabled sampled requests.

## Monitoring live-test plan

- Confirm all 14 alarms, their actions and OK actions, the encrypted alert
  topic, scoped policy, dashboard, and metric widgets exist.
- Use missing-secret/API 5xx behavior or another approved safe path to exercise
  the API 5xx metric and alarm without weakening a control.
- Use the single-message DLQ procedure to exercise the DLQ alarm and return it
  to OK only through reviewed cleanup.
- Use synthetic workflow states to exercise stale-queue,
  reconciliation-failure, manual-review-backlog, and expired-lease metrics.
- A Lambda `Errors` alarm requires a separately reviewed safe fault-injection
  method; do not break configuration merely to force an error.
- Validate SNS ALARM and OK publications technically. If direct alarm-state or
  metric injection is proposed, treat it as an explicit AWS mutation requiring
  separate approval and label the evidence as routing-only, not end-to-end
  application behavior.
- Confirm dashboard data is populated and data-minimized.

With zero subscriptions, SNS topic publication may pass while human delivery
remains untested and cannot be claimed.

## Rollback and failure handling

Rollback is never an automatic `terraform destroy`.

1. **Failed apply with partial creation:** stop; preserve output; inspect remote
   state and actual resources read-only; identify the last successful address;
   formulate a reviewed complete-forward, import, repair, or targeted rollback
   plan. Any state mutation requires separate approval.
2. **Successful apply with failed smoke tests:** stop test traffic and keep the
   system fail-closed. Compare configuration, state, logs, and resources. Fix
   forward through a reviewed plan unless a specific rollback is safer.
3. **Security-control failure:** declare NO-GO, stop public testing, and prepare
   an approved containment change such as a WAF deny posture or stage removal.
   Do not relax HMAC, WAF, logging, or ownership controls.
4. **Cost or unexpected-resource issue:** stop the activity creating usage,
   inventory charge drivers, and produce a reviewed plan. Do not manually
   delete resources behind Terraform.
5. **Secret-provisioning failure:** leave the endpoint fail-closed, correct the
   out-of-band key-ring document under approval, and retest. Never bypass HMAC
   or place a value in Terraform.

The DynamoDB table, SNS topic, both queues, and five log groups have
`prevent_destroy`. Removing those protections or destroying those resources
requires explicit owner review and a recovery/evidence-retention decision.

## Qualitative cost and resource safety

Likely recurring cost drivers are the WAF web ACL and managed rules, API Gateway
requests, Lambda invocations and duration, CloudWatch logs and ingestion, 14
alarms and one dashboard, DynamoDB on-demand requests/storage/PITR, SQS requests,
SNS publications, one Secrets Manager secret, and X-Ray traces. WAF, alarms,
dashboard, secret metadata, log retention, and stored DynamoDB/queue data can
incur cost even with little traffic.

API Gateway, Lambda, DynamoDB on-demand request capacity, SQS, SNS publication,
and X-Ray are generally usage-driven and should remain low when idle. This is a
qualitative review only; no monthly amount is asserted without traffic, log
volume, retention, and regional pricing assumptions. Unexpected traffic or log
growth is a stop-and-review condition.

## W3.8 live evidence plan

After an approved deployment, capture sanitized evidence for:

- final pre-apply plan summary, reviewed plan hash, approval, and apply result;
- post-apply 51-resource Terraform inventory, external-secret and external-IAM verification, and
  zero Wave 0–2 impact;
- API stage and WAF association;
- pre-secret fail-closed smoke tests;
- post-secret positive and negative HMAC tests without values/signatures;
- DynamoDB replay, idempotency, state, and concurrency outcomes;
- SQS retry, DLQ, queue-age, and manual-redrive readiness;
- alarm ALARM/OK transitions, SNS publication, subscription status, and later
  human-delivery confirmation;
- dashboard population and privacy-safe application/WAF/API log review;
- rollback readiness, `prevent_destroy` inventory, and final acceptance result.

Do not store state, binary plans, credentials, secret values, complete
signatures/digests/nonces, raw queue messages, request bodies, PHI, or PII.

## GO and NO-GO criteria

### GO for initial nonproduction apply

All of the following are mandatory:

- fresh recovery plan has zero destroy, replacement, unexpected update, or
  Secrets Manager operation and matches the reviewed remaining inventory;
- complete tests, Terraform checks, packaging, and sensitive review pass;
- no security blocker or unexpected existing-resource action exists;
- account-wide API Gateway logging impact is reconfirmed and accepted; and
- the project owner explicitly approves the reviewed plan and apply command.

Any missing criterion is a NO-GO.

### GO for live authentication testing

Infrastructure deployment must succeed, the endpoint must have demonstrated
fail-closed behavior before secret provisioning, logs must remain safe, and the
synthetic HMAC key ring must be provisioned through the separately approved
out-of-band process. Otherwise the live auth test is a NO-GO.

### GO for operational acceptance

Live API, WAF, DynamoDB, SQS/DLQ, monitoring, privacy, and recovery controls must
pass; an approved human alert destination must be subscribed and tested; and
operational runbooks and evidence must be reviewed. Clinical-system integration
remains a later-wave dependency and must not be represented as complete.

## Current gate decision

Wave 3 is **ENGINEERING CLOSED — DEPLOYMENT DEFERRED**. The security and
Terraform designs passed engineering validation, but the remaining 21 resources
were intentionally not deployed. Role existence, trust, reviewed policies,
expected boundaries, exact service-restricted PassRole authorization,
synthetic HMAC material, a human alert destination, and live control validation
remain incomplete. This is an owner-controlled governance boundary, not an
authorization to work around IAM controls.
