# Clinic/EMR Migration, CDC, Recovery, and Cutover Design

> Design validation only. No source was connected, no DMS task ran, no data was
> copied, and no clinical cutover or rollback was performed.

## Source-readiness gate

Before a real migration design could proceed, record and approve:

1. MySQL vendor/version support, topology, database size, change rate, peak load,
   storage engines, primary keys, LOB profile, schema objects, and dependencies.
2. Character sets, collations, SQL modes, time zones, zero dates, unsigned
   numeric ranges, generated columns, and data-type conversion risks.
3. Procedures, functions, triggers, events, views, grants, users, partitions,
   and DDL behavior that DMS will not safely convert or continuously replicate.
4. ROW binary logging, required row image, unique server ID, adequate binlog
   retention, DMS least-privilege user, TLS, certificate trust, and source
   performance headroom.
5. Exact table mappings and exclusions, retention/legal requirements, approved
   outage, clinical continuity procedure, RPO/RTO, and acceptable CDC lag.

Failure of any required compatibility or integrity condition is a no-go.

## Migration integrity validation

Use only owner-approved synthetic or properly governed validation tooling. Do
not export clinical row content to evidence.

| Control | Validation design |
|---|---|
| Row counts | Compare source/target counts by table and clinically meaningful partition |
| Primary identifiers | Confirm uniqueness and stable patient, appointment, encounter, and audit identifiers |
| Referential integrity | Check all declared and application-enforced relationships and orphan counts |
| Null/value distributions | Compare bounded aggregates and unexpected null/category shifts |
| Timestamps | Validate UTC/storage convention, DST edges, precision, and ordering |
| Encoding/collation | Exercise multilingual and edge-case synthetic strings; compare sort/equality behavior |
| Duplicate detection | Detect duplicated identities, encounters, appointments, and CDC replays |
| Deleted records | Confirm hard-delete, soft-delete, tombstone, and audit-history semantics |
| Clinical history | Compare version/order totals without exporting note or diagnosis content |
| Attachments | Match database references to FSx object identifiers, sizes, and checksums |
| Audit continuity | Verify sequence/order, actor mapping, timestamps, and protected retention |

Every mismatch is classified, traced, and either resolved or explicitly blocks
go-live. Aggregate evidence must not contain patient identifiers.

## CDC validation matrix

| Scenario | Expected design outcome |
|---|---|
| Insert propagation | One target row and matching audit event after bounded lag |
| Update propagation | Correct version/order with no lost fields or stale target state |
| Delete propagation | Approved hard/soft-delete semantics preserved and auditable |
| High-change interval | No source overload, queue exhaustion, or silent data loss |
| Replication lag | Source/target metrics alert; cutover blocked above approved threshold |
| DMS restart | Resume from checkpoint without duplicate or missing changes |
| Network interruption | Recover with bounded retry; validate checkpoint and reconciliation |
| Duplicate prevention | Primary/idempotency constraints reject replay side effects safely |
| DDL during CDC | Change freeze or separately tested handling; unapproved DDL blocks cutover |
| Source/target reconciliation | Counts, hashes/aggregates, identifiers, and audit markers agree |

The exact acceptable cutover lag is **OWNER / CLINICAL DECISION REQUIRED**.
The Terraform alarm uses 300 seconds only as a visible design placeholder, not
an approved clinical threshold.

## Conceptual cutover procedure

1. **Readiness checks:** require source inventory, schema conversion, full-load
   validation, restore rehearsal, clinical continuity plan, monitoring, access,
   rollback ownership, and signed change record.
2. **Freeze/change-control:** prohibit schema/permission changes and confirm all
   applications, integrations, jobs, and users governed by the window.
3. **Full-load completion:** verify all selected tables completed without
   suspended tables, truncation, validation failures, or unreviewed exclusions.
4. **Monitor CDC:** establish stable replication, source health, and bounded lag.
5. **Final source-write freeze:** stop Clinic/EMR and integration writes while
   maintaining the approved downtime workflow and audit custody.
6. **Catch up:** wait for zero or owner-approved lag and a stable checkpoint.
7. **Integrity validation:** execute the complete control set and attachment
   reference checks using protected aggregate evidence.
8. **Connection switch:** change only reviewed application secret/configuration
   references; never expose RDS or bypass TLS.
9. **Role smoke/UAT:** doctors, nurses, reception, managers, IT, security, and
   break-glass validators execute the approved synthetic matrix.
10. **Go/no-go:** require clinical, security, vendor, data, recovery, and
    operational sign-off. Silence or an unresolved discrepancy is no-go.
11. **Reconcile:** compare final source/target markers, downtime transactions,
    integrations, attachments, audit sequences, and rejected work.

No step above was executed in Wave 5.

## Rollback rehearsal design

Rollback criteria include integrity mismatch, missing clinical history,
unacceptable CDC lag, major application or authentication failure, audit loss,
FSx/database inconsistency, critical performance degradation, or inability to
reconcile downtime transactions.

Conceptual response:

1. Stop target writes and integrations; preserve target state, logs, metrics,
   task checkpoints, test results, and decision evidence.
2. Determine whether any target-only transaction exists. Never silently discard
   a clinical change made during the attempted cutover.
3. Return applications to the source using the reviewed secret/configuration
   reversal, then validate source integrity and authentication before reopening.
4. Reconcile captured downtime and target-only transactions through a
   clinically approved manual process with dual review.
5. Record root cause and decide through change governance whether to forward-fix
   or schedule a later retry.

This rollback is a design; it was not rehearsed live.

## Backup and restore design

- Seven-day RDS automated backups and point-in-time recovery.
- Owner-approved manual snapshot immediately before cutover.
- Daily AWS Backup design with 35-day retention for EC2/EBS, RDS, and optionally
  externally managed FSx when explicitly included.
- Encrypted vault and snapshots under an external KMS key; deletion and backup
  administration are separated and monitored.
- Restore into an isolated private environment without live integrations.
- Validate database consistency, row/control totals, clinical workflows, audit
  continuity, attachment checksums, authorization, and recovery timing.

RPO 15 minutes and RTO four hours are portfolio assumptions only. Owner,
clinical, vendor, and recovery stakeholders must approve real objectives.
