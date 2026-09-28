# Wave 4 Security Review

Permanent deployment status: **DESIGN VALIDATED — NOT DEPLOYED**. **NEVER DEPLOY**
this Wave 4 design package.

## Findings

| Classification | Finding | Required treatment |
|---|---|---|
| BLOCKER | No commercial Pharmacy package, vendor support matrix, schema, or integration contract was supplied | Never represent functional or migration compatibility as proven |
| BLOCKER | Private subnets have no SSM/provider egress path beyond S3 | A future live design would require approved interface endpoints and controlled provider egress; no NAT shortcut |
| DESIGN REQUIREMENT | RDS must remain private and accept TCP/1433 only from the application SG | Enforced in design and static tests |
| DESIGN REQUIREMENT | EC2 administration must use Session Manager with no routine RDP | Enforced in design and static tests |
| DESIGN REQUIREMENT | SQL client must require TLS and validate the RDS certificate | Confirm vendor driver and connection configuration |
| DESIGN REQUIREMENT | IAM roles, KMS key, database secret, and backup role remain externally governed | Owner supplies and reviews exact-purpose identities and policies |
| DESIGN REQUIREMENT | Restore integrity and prescription/audit reconciliation must precede acceptance | Use the synthetic validation matrix and recorded control totals |
| DESIGN CONSTRAINT | Single-AZ pilot can experience AZ-level downtime | Accepted only for portfolio/nonproduction design; not a production recommendation |
| DESIGN CONSTRAINT | Directory authentication support is unverified | Validate edition, region, DNS, IAM integration role, and client behavior; otherwise use rotated external secret credentials |
| DESIGN CONSTRAINT | Existing FSx is not an assumed dependency | Add SMB only if vendor evidence requires it and then scope TCP/445 exactly |
| DESIGN CONSTRAINT | No VPN or clinic-client path is evidenced | Define private client connectivity before any future implementation design |
| COST CONSIDERATION | SQL Server licensing and Windows EC2 dominate steady cost | Keep conceptual pilot small; validate vendor minimums |
| COST CONSIDERATION | NAT, Transfer Family, and interface endpoints add fixed hourly cost | Baseline omits NAT/Transfer; add only evidenced endpoints |
| FOLLOW-UP | Confirm audit retention, immutable archive, legal hold, RPO, and RTO | Obtain security, clinical, and records-owner decisions |
| FOLLOW-UP | Confirm provider authentication, allowlisting, idempotency, callbacks, timeout, and reconciliation | Prefer outbound HTTPS; retain callback/SFTP alternatives only when required |

## Static control conclusions

- No public RDS access or public EC2 address is modeled.
- No inbound RDP, broad SQL CIDR, default-route provider allowlist, FTP, NAT,
  IAM role, Secrets Manager resource, or secret value is modeled.
- EC2 storage, RDS storage, CloudWatch logs, and backup vault reference an
  externally governed KMS key.
- RDS automated backups, AWS Backup, final snapshot, deletion protection, and
  lifecycle protection are modeled.
- Security groups default to no inbound and allow only exact modeled flows.
- The design does not prove vendor compatibility, operational recovery, live
  provider connectivity, clinical UAT, or real data integrity.
