# Appointment API application foundation

This W3.2 package proves the Lambda deployment and event contracts without
implementing production HMAC verification or clinical-system behavior.

## Safety boundary

- The intake handler validates basic content type and JSON shape, emits only
  approved operational metadata, and returns a `FOUNDATION_ONLY` response.
- It does not persist the request, enqueue work, or claim that an appointment
  was created.
- The worker validates the minimum SQS envelope and performs no clinical action.
- The reconciler emits a scheduled heartbeat and performs no workflow mutation.
- Production HMAC, nonce, idempotency, and durable workflow operations are
  deferred to W3.3.

## Request-schema assumptions

`patientReference` is a synthetic or pre-existing opaque identifier. Contact
details remain in an approved upstream or authoritative system and are not
accepted by this API contract. The schema intentionally omits diagnosis,
treatment notes, prescriptions, laboratory/radiology results, payment-card
data, credentials, secrets, and arbitrary free text.

## Build contract

Run `build.ps1` to create `dist/appointment-api.zip`. The generated `dist/`
directory is ignored by Git. The ZIP contains the `intake`, `worker`,
`reconciler`, and `common` packages at its root so the Terraform handler names
resolve correctly.

No dependency installation or secret material is required for this foundation.
