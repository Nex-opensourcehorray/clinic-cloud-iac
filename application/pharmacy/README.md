# Wave 4 Pharmacy Migration Design

> **Permanent status:** DESIGN VALIDATED — NOT DEPLOYED. This package is
> portfolio architecture and security evidence. It does not describe a live
> Pharmacy application, deployed EC2 instance, deployed RDS database, completed
> migration, or operationally accepted workload. **NEVER DEPLOY** this Wave 4
> design package.

## Evidence boundary and assumptions

Repository evidence supports these existing facts:

- AWS account `119033255630`, region `ap-east-1`.
- DNS-enabled VPC `vpc-0dfbc450b3120b16c`, CIDR `10.0.0.0/16`.
- Private subnets `subnet-0c7ffc0456bbfcb56` in `ap-east-1a` and
  `subnet-06836be6443e37a7c` in `ap-east-1b` have no default route.
- The only evidenced endpoint is S3 gateway endpoint
  `vpce-02c654afe0052628a`.
- AWS Managed Microsoft AD and Windows FSx exist externally; the Directory
  Service controller security group is `sg-0f43ac70d383b4859` and repository
  evidence references directory `d-c4677826f0` and FSx
  `fs-0c520115e42a87b17`.
- No approved backup policy, VPN path, NAT gateway, SSM interface endpoints,
  controlled internet-egress path, Pharmacy IAM roles, Pharmacy secret, or
  Pharmacy KMS key is evidenced.

The following are explicit portfolio assumptions requiring vendor and owner
validation:

- A commercial Pharmacy application has not been supplied or tested.
- The application can run on a supported patched Windows Server EC2 image.
- Its database engine is supported on Amazon RDS for SQL Server Express for the
  pilot; edition, version, feature, collation, SQL Agent, and licensing needs
  remain unknown.
- The application supports TLS database connections and idempotent provider
  integration.
- Prescription data is confidential regulated information; examples and tests
  use synthetic data only.
- An RPO target of 15 minutes and an RTO target of four hours are design
  assumptions, not approved clinical requirements.
- Existing Directory Service compatibility, DNS forwarding, and RDS Windows
  Authentication support must be confirmed before selecting directory auth.
- A pharmacy/provider contract, endpoint inventory, certificates, IP
  allowlists, SFTP need, retry semantics, and downtime tolerance do not exist in
  project evidence.

## Architecture

```text
Authorized clinic user
        |
        | private clinic connectivity (not yet evidenced)
        v
Private Windows EC2 application tier
  - no public IP
  - no inbound RDP
  - Session Manager through external interface endpoints
  - encrypted gp3 EBS
        |
        | TLS TCP/1433, application SG -> database SG only
        v
Private RDS for SQL Server Express, Single-AZ pilot
  - publicly_accessible = false
  - encrypted gp3 storage
  - automated backups and final snapshot protection
        |
        +--> encrypted backup vault / restore validation
        |
        +--> audit and operational logs

Application --> controlled outbound HTTPS --> pharmacy/provider API
                 (route/proxy and provider contract are design prerequisites)
```

The design creates no public application path, fixed public database address,
routine RDP rule, NAT gateway, FTP service, Transfer Family endpoint, IAM role,
or secret value. Existing FSx is not assumed to be required. The existing S3
gateway endpoint does not provide SSM, CloudWatch, KMS, Secrets Manager, or
public provider connectivity.

## Application tier

- One conceptual `t3.small` Windows EC2 instance for portfolio clarity and
  cost-conscious nonproduction sizing. Vendor sizing can supersede it.
- Private subnet, no public IPv4 address, IMDSv2 required, hop limit one.
- Encrypted 50 GiB gp3 root volume using an externally governed KMS key.
- No inbound security-group rule. Administration is Session Manager only.
- External instance profile supplies least-privilege SSM, telemetry, KMS, and
  exact Pharmacy-secret read permissions. Terraform does not create IAM.
- Detailed EC2 monitoring and an encrypted 90-day application log group.
- No application payload, prescription detail, credential, or token in logs.
- Patching uses an owner-approved golden AMI and Systems Manager maintenance
  workflow; no in-place exception is assumed.

Session Manager is not currently reachable from the evidenced private route
tables. A live design would require externally governed interface endpoints for
`ssm`, `ssmmessages`, and `ec2messages`; telemetry and secrets normally also
require `logs`, `monitoring`, `kms`, and `secretsmanager`, or a separately
approved controlled-egress design. The baseline prefers endpoints over NAT.

## Database tier

- Amazon RDS for SQL Server Express, conceptual `db.t3.small`, Single-AZ.
- Two-private-subnet DB subnet group, no public accessibility.
- SQL TCP/1433 accepted only from the Pharmacy application security group.
- 20 GiB encrypted gp3 storage with limited autoscaling to 50 GiB.
- Seven-day automated backup retention, encrypted snapshots, deletion
  protection, final snapshot, and `prevent_destroy` in the design module.
- Automatic minor-version upgrades and scheduled maintenance windows.
- Error and SQL Agent logs exported to CloudWatch where supported.
- TLS is mandatory at the client; certificate validation and driver behavior
  must be confirmed with the vendor.
- SQL Server Audit to an encrypted, immutable log archive is a design
  requirement. Exact option-group support depends on edition/version and is a
  follow-up rather than a fabricated Terraform resource.

Directory authentication is preferred only if the selected RDS edition,
`ap-east-1` availability, application driver, AWS Managed Microsoft AD, DNS,
and external directory IAM role are all validated. Otherwise, use a dedicated
least-privilege SQL login stored in an externally governed Secrets Manager
secret and rotated through an owner-approved process. Terraform accepts the
secret ARN as a contract and never reads or manages its value. The RDS bootstrap
password interface is ephemeral and write-only so a hypothetical deployment
would not persist it in state; no value is supplied in this repository.

## Network and security-group flow

| Source | Destination | Protocol/port | Purpose | Status |
|---|---|---:|---|---|
| Pharmacy application SG | Pharmacy database SG | TCP/1433 | TLS SQL Server connection | Modeled |
| Pharmacy application SG | External SSM endpoint SG | TCP/443 | Session Manager | Input contract; endpoints not evidenced |
| Pharmacy application SG | Exact provider/egress CIDRs | TCP/443 | Provider API | Empty until contract exists |
| Any public CIDR | Application or database | Any | Public/RDP/database access | Prohibited |
| Application | Existing FSx | SMB/445 | Not assumed | Not modeled |

No `0.0.0.0/0` egress rule is accepted by the provider CIDR input. DNS-aware
allowlisting generally requires a controlled proxy or firewall because provider
addresses can change; fixed CIDR rules alone are not a durable API control.

## Identity and secret ownership

- IAM administration remains owner-controlled and external to Terraform.
- The external EC2 role must permit only SSM core-channel operations,
  telemetry writes, decrypt under the exact KMS key where needed, and
  `secretsmanager:GetSecretValue` for the exact Pharmacy secret.
- AWS Backup uses an externally governed exact-purpose service role.
- No AdministratorAccess, PowerUserAccess, broad `iam:*`, access key, local
  administrator password, database password, or secret value belongs in code,
  state, user data, logs, or evidence.
- Human database administration uses named MFA-backed identities and audited
  elevation; shared SQL administrator use is limited to break-glass recovery.

## Provider integration options

| Option | Authentication and encryption | Network path | Reliability and audit | Assessment |
|---|---|---|---|---|
| Outbound HTTPS API | mTLS or OAuth client credentials from external secret; TLS 1.2+ | Controlled proxy/firewall or exact provider endpoint over TCP/443 | Bounded timeout, idempotency key, exponential backoff, dead-letter/manual reconciliation, sanitized request ID logs | **Preferred baseline** |
| Provider callback | Signed webhook or mTLS; TLS 1.2+ | Requires a separately designed authenticated ingress boundary, WAF/rate limits, replay protection, and no direct EC2 exposure | Durable receipt, nonce/timestamp checks, idempotency, audit correlation | Alternative only with justified inbound requirement |
| SFTP | SSH host-key pinning and key in external secret | Outbound TCP/22 to exact provider allowlist; managed transfer boundary preferred | Atomic filenames, checksums, manifests, polling/retry, quarantine and reconciliation | Only if vendor cannot support API |

FTP is prohibited. Static outbound IP and NAT are not baseline requirements;
they become cost and architecture decisions only if a provider proves IP
allowlisting is mandatory. Transfer Family is not modeled unless SFTP is a
confirmed requirement.

## Cost considerations

No Wave 4 resource will be provisioned, so this is a qualitative driver review:

- RDS for SQL Server license-included runtime is likely the largest steady
  driver even at a small class.
- Windows EC2, EBS, RDS gp3 storage, automated backups, AWS Backup retention,
  CloudWatch ingestion/retention, KMS requests, and snapshots add recurring
  costs.
- NAT Gateway and Transfer Family have meaningful fixed hourly costs and are
  deliberately absent from the baseline.
- Interface endpoints have per-AZ hourly and data-processing costs; they are
  preferred for private administration but should be limited to evidenced
  services.
- Single-AZ reduces portfolio cost but is an availability constraint and is
  not a production recommendation.

## Terraform design boundary

`modules/pharmacy` models EC2, RDS, narrow security groups, monitoring, and
backup controls. `environments/design/pharmacy` validates it with placeholders
and no backend. It contains no IAM role, secret resource, NAT gateway, VPC
endpoint, public IP, RDP rule, or provider transfer service.

The Terraform is never deployment authorization. No plan is required for Wave
4 closure, no saved plan may be reused, and `terraform apply` is permanently
prohibited.
