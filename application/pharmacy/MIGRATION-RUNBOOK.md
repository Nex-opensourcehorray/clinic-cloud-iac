# Pharmacy Migration, Recovery, and Validation Runbook

> Portfolio design only. No migration, backup operation, cutover, restore, or
> AWS resource mutation was performed.

## Backup and restore design

Conceptual controls:

- RDS automated backups retained seven days with point-in-time recovery.
- Owner-approved manual snapshot before schema, engine, or cutover change.
- Daily AWS Backup recovery points retained 35 days for EC2/EBS and RDS,
  encrypted with an externally governed KMS key.
- Final RDS snapshot and deletion protection; design lifecycle prevents
  accidental destroy.
- Quarterly isolated restore exercise using synthetic data.
- Integrity validation covers row counts, prescription-state totals, audit
  sequence continuity, foreign keys, checksums where supported, and application
  read/write behavior.

Assumed targets are RPO 15 minutes and RTO four hours. Business owners, vendor
support, database size, log generation, and provider recovery dependencies must
validate both before any real migration design is approved.

### Restore validation sequence

1. Select an approved recovery point without exposing production data.
2. Restore into an isolated private test boundary with no provider integration.
3. Apply current parameter, option, SG, encryption, and logging controls.
4. Run database consistency checks and compare synthetic control totals.
5. Validate prescription lifecycle and immutable audit ordering.
6. Confirm credentials, certificates, and external integrations remain disabled.
7. Record actual restore time, recovery point, integrity results, and exceptions.
8. Destroying the isolated restore would require a separate approved process;
   no cleanup mutation is part of Wave 4.

## Portfolio cutover design

1. **Pre-cutover:** confirm backups, restore rehearsal, approved change window,
   source/target versions, schema mapping, certificates, provider sandbox,
   monitoring, rollback ownership, and synthetic validation scripts.
2. **Freeze:** announce downtime and stop new prescription mutations at the
   source while retaining read-only access and audit evidence.
3. **Final synchronization:** use a vendor-supported encrypted native
   backup/restore or a separately designed replication method; record control
   totals and the final source transaction marker.
4. **Validate:** run database integrity checks, authentication, application
   startup, prescription create/amend/dispense workflows, audit continuity, and
   provider sandbox connectivity.
5. **Go/no-go:** require security, functional, data-integrity, recovery, vendor,
   and clinical-owner sign-off. Silence is a no-go.
6. **Cut over:** change only the approved private application/configuration
   boundary; never expose RDS or bypass TLS.
7. **Rollback:** stop target writes, preserve target evidence, restore source
   service, reverse only reviewed routing/configuration, and verify source
   integrity before reopening.
8. **Reconcile:** compare source and target transaction markers, prescriptions,
   amendments, dispense states, acknowledgements, failures, and audit events;
   route discrepancies to manual review.

No live cutover, DNS change, database copy, DMS task, transaction freeze, or
provider call occurred in Wave 4.

## Functional and failure-path matrix

All future cases use synthetic identifiers and data.

| Test | Expected result |
|---|---|
| Prescription create | One authorized durable prescription and one audit event chain |
| Amendment | Authorized versioned change; prior value remains auditable |
| Dispense | Legal state transition, actor/time recorded, no duplicate dispense |
| Duplicate create | Idempotency returns the authoritative existing transaction |
| Provider retry | Bounded retry with the same idempotency/correlation key |
| Provider permanent failure | Safe pending/manual-review state; no false success |
| Provider timeout/unknown result | Reconciliation before resubmission |
| Unauthorized user | Denied before data mutation; sanitized audit record |
| Database unavailable | Fail closed, no lost local success claim, recovery alert |
| TLS or certificate failure | Connection rejected; no plaintext fallback |
| Audit-log failure | Security alert and controlled failure according to vendor behavior |
| Backup restore | Integrity checks and synthetic workflows pass in isolation |
| Downtime fallback | Approved manual continuity procedure with later reconciliation |
| Rollback | Source restored without accepting target-only transactions silently |
| Post-cutover reconciliation | Counts, states, acknowledgements, and audit markers agree |

## Migration method decision

Native SQL Server backup/restore is the preferred portfolio baseline when a
bounded outage is acceptable and vendor support confirms compatibility. A
full-load plus CDC approach would require separate DMS design, source logging,
LOB, collation, identity, and cutover-lag validation. DMS is not assumed or
created in Wave 4.
