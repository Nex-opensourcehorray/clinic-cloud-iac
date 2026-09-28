# Portfolio Evidence Handling

The tracked evidence in this directory is a sanitized portfolio copy. It
preserves observed control results, resource types, relationships, regions,
availability-zone concepts, and relevant CIDRs while removing unnecessary
live nonproduction fingerprints.

Common placeholders include:

| Placeholder | Meaning |
|---|---|
| `<AWS_ACCOUNT_ID>` | Portfolio AWS account identifier |
| `<AWS_SERVICE_ACCOUNT_ID_*>` | AWS-owned or external service account identifier captured in discovery |
| `vpc-<REDACTED>` | Existing nonproduction VPC |
| `subnet-<PUBLIC_A>` / `subnet-<PRIVATE_A>` | Subnet role and Availability Zone grouping |
| `rtb-<PUBLIC>` / `rtb-<PRIVATE_A>` | Route-table role |
| `sg-<...>` | Security-group role |
| `<PRIVATE_IP>` / `<PRIVATE_DNS_NAME>` | Private host address or name |
| `<LOCAL_REPOSITORY>` / `<PRIVATE_ARCHIVE>` | Local workstation or non-public archive location |

The original operational evidence is not published merely to preserve hash
continuity. Hash sidecars next to modified artifacts identify the digest of the
sanitized portfolio copy. The removed W2.5.7 Terraform-state snapshot is
represented by a derived ownership summary; it is not Terraform state.
