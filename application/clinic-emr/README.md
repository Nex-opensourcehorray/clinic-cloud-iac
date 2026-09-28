# Wave 5 Clinic/EMR Shared MySQL Migration Design

> **Permanent status:** DESIGN VALIDATED — NOT DEPLOYED. This is portfolio
> architecture, security, and migration-validation evidence only. It is not a
> live Clinic/EMR system, migration, cutover, or clinical acceptance record.
> **NEVER DEPLOY** this Wave 5 design package.

## Evidence boundary and workload assumptions

Known portfolio facts:

- Clinic Management and EMR share a MySQL datastore and must migrate together
  to prevent cross-system inconsistency.
- Clinical roles include doctors, nurses, reception, clinic managers, IT,
  security, and explicitly controlled break-glass users.
- PHI, PII, clinical history, audit continuity, and patient matching are
  high-integrity requirements.
- Repository evidence identifies AWS account `119033255630`, region
  `ap-east-1`, VPC `vpc-0dfbc450b3120b16c` (`10.0.0.0/16`), two private
  subnets without default routes, S3 gateway endpoint
  `vpce-02c654afe0052628a`, AWS Managed Microsoft AD, and Windows FSx
  `fs-0c520115e42a87b17`.
- IAM roles, permissions boundaries, KMS keys, and secret containers follow the
  existing external owner-controlled governance model.

Unknown and requiring source/vendor/owner confirmation:

- Commercial Clinic/EMR product and vendor support constraints.
- Exact MySQL version, schema, size, change rate, topology, storage engine,
  primary keys, and binlog configuration.
- Stored procedures, triggers, events, views, grants, partitions, generated
  columns, unsupported data types, and large-object distribution.
- Character sets, collations, time zones, zero-date behavior, and application
  connection/TLS behavior.
- Exact on-premises source route, VPN path, firewall rules, DNS, source impact
  tolerance, and provider/integration requirements.
- Production RPO, RTO, acceptable CDC lag, downtime, audit retention, and
  legal-hold requirements.

No compatibility, performance, migration, UAT, restore, or clinical outcome is
claimed as proven.

## Target architecture

```text
Authorized clinical users over approved private connectivity
                 |
                 v
Private Clinic/EMR application EC2
  - no public IP, no SSH/RDP ingress
  - Session Manager via external interface endpoints
  - encrypted gp3 EBS and sanitized monitoring
       | TLS TCP/3306 (application SG -> database SG)
       v
Private RDS MySQL, Single-AZ design baseline
  - publicly_accessible = false
  - encrypted gp3, backups, final snapshot, deletion protection
       |
       +--> existing FSx over SMB only if vendor evidence requires files

Migration-only path:
Source MySQL -- private TLS TCP/3306 --> private DMS
Private DMS  -- private TLS TCP/3306 --> RDS MySQL
                 full load + CDC + validation
```

The application and database have no public address. The design has no
inbound SSH/RDP, no direct clinical-user database access, no broad database
CIDR, no NAT, no endpoint creation, and no live nonproduction integration.

## RDS MySQL design

| Topic | DESIGN CHOICE | REQUIRES SOURCE/VENDOR CONFIRMATION |
|---|---|---|
| Engine | RDS MySQL 8.0 conceptual baseline | Exact supported source/target versions and upgrade path |
| Sizing | `db.t3.small`, 20 GiB gp3, autoscaling ceiling 100 GiB | Working set, IOPS, connection count, peak concurrency, growth |
| Availability | Single-AZ portfolio/nonproduction scenario | Clinical availability requirement and Multi-AZ need |
| Network | Private two-subnet group; application/DMS SGs only on TCP/3306 | Private source route, DNS, client behavior |
| Encryption | External KMS key; TLS required with certificate validation | Driver and vendor certificate trust behavior |
| Parameters | Dedicated `mysql8.0` group with `require_secure_transport=1` | Charset, collation, time zone, SQL mode, max connections |
| Recovery | Seven-day automated backups, final snapshot, deletion protection, `prevent_destroy` | Approved retention, RPO/RTO, legal hold |
| Logs | Encrypted error logs and metrics; no intentional clinical payload logging | Audit-plugin support and approved protected-log destination |

The bootstrap password input is ephemeral and write-only. Application and DMS
credentials are external secret-ARN contracts. The design never stores secret
values in code, state, evidence, user data, or logs.

## DMS full-load and CDC design

- A private Single-AZ `dms.t3.small` conceptual replication instance uses the
  two private subnets and a dedicated security group.
- Source and target MySQL endpoints use externally governed Secrets Manager
  ARNs, an exact-purpose external DMS access role, and external certificate ARNs.
- Endpoint TLS is modeled as `verify-full`; hostname and trust-chain behavior
  must be tested before any real task.
- The task uses `full-load-and-cdc`, explicit schema selection, limited LOB mode,
  validation, conservative parallelism, default-severity logs, bounded retry,
  and fail-closed task stops for data, truncation, or table errors.
- Table mappings must be regenerated from a reviewed inventory. `%` under the
  explicitly named application schema is a design placeholder, not authorization
  to migrate system schemas or every source database.

Source prerequisites include ROW binlog format, full row images where required,
stable server IDs, adequate binlog retention, DMS replication privileges,
consistent time zones, supported storage engines, and primary or unique keys.
Exact settings depend on the source/version and are not asserted here.

DMS does not migrate all schema objects or server configuration. Procedures,
functions, triggers, events, users/grants, scheduled work, and some data types or
DDL require separate inventory, conversion, deployment, and validation. Triggers
must not produce duplicate side effects during full load/CDC or cutover.

LOB mode and its 32 KiB conceptual limit require data profiling; data or
truncation errors stop the task rather than silently accepting loss. DMS operational
logs must contain identifiers and metrics only where configurable—never patient
names, clinical notes, payloads, SQL literals, or secret material.

## Data classification

| Data | Classification | Handling design |
|---|---|---|
| Patient demographics and identifiers | PHI + PII | Restricted, encrypted, least privilege, audited |
| Appointments | PHI + operational | Preserve identifiers, time zones, status history |
| Encounters, notes, diagnoses, medication history | PHI / clinical record | Highest-integrity validation; never log content |
| Billing references | PHI/PII + financial reference | Minimize and reconcile referential links |
| User/account metadata | PII + security metadata | Directory correlation, least privilege, no password migration |
| Audit history | Security/audit + possible PHI | Append-oriented, protected retention, access review |
| Attachments and file references | PHI + integrity metadata | Encrypt files; reconcile database reference to file object |
| DMS metrics and task state | Operational/security metadata | Sanitized logging with restricted access |

Evidence and test designs contain no real or synthetic patient records.

## Network and administration

| Source | Destination | Protocol | Purpose |
|---|---|---|---|
| Application SG | Database SG | TLS TCP/3306 | Clinic/EMR transactions |
| DMS SG | Database SG | TLS TCP/3306 | Target full load and CDC |
| DMS SG | Exact private source CIDRs | TLS TCP/3306 | Source full load and CDC |
| Application/DMS SGs | Exact private resolver | UDP/TCP 53 | DNS |
| Application/DMS SGs | External service-endpoint SG | TCP/443 | SSM, logging, KMS, secrets |
| Application SG | External FSx SG | TCP/445 | Optional vendor-required shared files |
| Application SG | Exact integration CIDRs | TCP/443 | Approved external integration |

The currently evidenced private routes provide only S3 gateway access. A real
implementation would require separately governed SSM/logging/KMS/Secrets
Manager endpoints and an approved on-premises source path. This module creates
none of them. Administration is Session Manager; there is no routine SSH/RDP.

## Identity and secret ownership

- Application, DMS secret-access, and AWS Backup roles are externally managed.
- Secrets metadata and values are externally managed and rotated through an
  owner-approved process; the design consumes only exact ARNs.
- The application role is limited to SSM channels, telemetry, exact KMS use,
  and exact application-secret read.
- The DMS role is limited to the source/target secrets and required KMS use.
- Database bootstrap, schema administration, migration, backup, application,
  and human break-glass duties remain separated.
- Clinical users authenticate to the application and receive application-layer
  RBAC. They receive no direct MySQL login.

## FSx and shared-file consistency

Existing FSx is only a conceptual reuse option when vendor evidence requires
SMB for reports, attachments, exports, or legacy paths. Structured records,
patient/encounter identifiers, and attachment metadata remain in MySQL while
binary content may remain on encrypted FSx. The database reference and file
object must be validated together by stable identifier, size, checksum, and
access policy. Orphans, duplicates, missing files, and point-in-time mismatch
must block acceptance. The design does not assume all clinical content belongs
in MySQL or that existing FSx is compatible.

## Cost considerations

No Wave 5 AWS resource will be created. Hypothetical drivers are RDS MySQL
runtime and storage, private EC2 and EBS, temporary DMS replication runtime and
storage, CloudWatch ingestion/retention, KMS operations, AWS Backup retention,
snapshots, interface endpoints, data transfer, and optional FSx capacity and
backup. DMS is temporary in a real migration and would be removed only after
evidence, reconciliation, acceptance, and separate authorization.

## Terraform boundary

`modules/clinic-emr` models a design-only application, RDS, DMS, narrow SGs,
monitoring, and backup. `environments/design/clinic-emr` validates it with
placeholders and no backend. It creates no IAM role, secret, VPC route, NAT,
endpoint, VPN, or active nonproduction connection. No plan or apply is required
or authorized.
