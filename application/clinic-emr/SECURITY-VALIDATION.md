# Wave 5 Clinic/EMR Threat and Security Review

Permanent deployment status: **DESIGN VALIDATED — NOT DEPLOYED**. **NEVER DEPLOY**
this Wave 5 design package.

## Findings

| Classification | Threat/finding | Required treatment |
|---|---|---|
| BLOCKER | No vendor, schema, source version, size/change-rate, or feature inventory exists | Compatibility, conversion, sizing, and DMS mappings cannot be represented as proven |
| BLOCKER | No approved private source route/VPN or interface endpoints are evidenced | Validate redundant hybrid path, DNS, firewall, endpoint, telemetry, and secret access before implementation design |
| BLOCKER | Production RPO/RTO, acceptable CDC lag, downtime, and clinical continuity are unapproved | Owner and clinical decisions are required; Terraform thresholds are placeholders |
| DESIGN REQUIREMENT | RDS and DMS must remain private; application/DMS SGs are the only TCP/3306 sources | Enforced in module and static tests |
| DESIGN REQUIREMENT | Clinical users must use application RBAC, never direct database accounts | Validate role matrix, negative tests, separation of duties, and audit evidence |
| DESIGN REQUIREMENT | Secrets and IAM remain externally governed and least privilege | Exact role/secret/KMS contracts; no credentials in Terraform, logs, or evidence |
| DESIGN REQUIREMENT | Source/target endpoint TLS uses hostname/certificate verification | External certificate lifecycle and vendor trust behavior require testing |
| DESIGN REQUIREMENT | DMS validation supplements but does not replace independent integrity checks | Block on missing keys, truncation, suspended tables, mismatches, or audit loss |
| DESIGN REQUIREMENT | Migration and application logs exclude clinical payloads and secrets | Default severity, protected retention, restricted access, content review |
| DESIGN REQUIREMENT | Backup deletion and KMS administration are separated and monitored | External governance plus isolated restore and integrity exercises |
| DESIGN REQUIREMENT | Break-glass activation is explicit, strongly authenticated, alerted, reasoned, and reviewed | No standing/shared emergency account |
| DESIGN CONSTRAINT | Single-AZ EC2/RDS/DMS is a cost-conscious portfolio scenario | Not a production availability recommendation |
| DESIGN CONSTRAINT | Existing FSx compatibility and necessity are unknown | Use only with vendor evidence; reconcile file object and DB reference atomically |
| DESIGN CONSTRAINT | DMS does not migrate every schema object, user/grant, trigger, routine, event, or server setting | Inventory and separately deploy/validate supported transformations |
| FOLLOW-UP | Profile LOB sizes, charsets/collations, time zones, data types, source impact, and CDC retention | Replace conceptual defaults with measured requirements |
| FOLLOW-UP | Define immutable clinical/audit retention, legal hold, access reviews, and ransomware recovery | Obtain clinical, privacy, records, security, and recovery decisions |

## Threat conclusions

- **Public database exposure:** prohibited through private subnets,
  `publicly_accessible = false`, and SG-reference-only target access.
- **Credential compromise:** secrets and DMS access role are external and exact;
  bootstrap password is ephemeral/write-only; no user receives shared DB access.
- **Excessive privileges:** clinical RBAC is application-layer, platform duties
  are separated, and DMS permissions are limited to migration endpoints.
- **Ransomware/backup deletion:** external KMS and backup administration,
  protected snapshots, isolated restore, and deletion monitoring are required.
- **DMS endpoint secret exposure:** ARNs only in Terraform; values never appear
  in code, task settings, state, evidence, or logs.
- **Migration-log PHI leakage:** task logs use default severity and must be
  content-reviewed; no row payload or SQL literal belongs in evidence.
- **CDC integrity failure:** lag, restart, interruption, duplicate, delete, and
  reconciliation tests gate cutover; exact lag remains owner-decided.
- **Unauthorized schema changes:** schema freeze and change control begin before
  full load and continue through reconciliation.
- **Audit-loss risk:** audit continuity is a go/no-go control; a missing event or
  failed protected sink blocks acceptance.
- **Insecure rollback:** target writes stop, target-only changes are reconciled,
  evidence is preserved, and source integrity is revalidated before reopening.
- **Break-glass misuse:** every activation is time-bound, alerted, reasoned, and
  reviewed; routine use is prohibited.
- **Shared-file/database inconsistency:** stable references, checksums, orphan
  detection, aligned recovery points, and dual-system reconciliation are required.

No live security test, migration, UAT, restore, rollback, or AWS mutation was
performed. The conclusions validate design controls only.
