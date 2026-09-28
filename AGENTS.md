# Clinic Cloud IaC — Codex Operating Rules

## Project

This repository implements the Healthcare Cloud Security Engineering Project:
Secure AWS Migration for a Clinic Management System.

The project uses Terraform and AWS.

Current implementation status:

- Wave 0: CLOSED
- Wave 1: CLOSED
- Wave 2: CLOSED — PASS
- Wave 3: ENGINEERING CLOSED — DEPLOYMENT DEFERRED
- Wave 4: DESIGN VALIDATED — NOT DEPLOYED
- Wave 5: DESIGN VALIDATED — NOT DEPLOYED
- Wave 6: DISCOVERY CLOSED — IMPLEMENTATION TERMINATED

Wave 6 ended because the required external ISP/private-connectivity prerequisite
was unavailable. Authenticated read-only discovery found an existing VGW-based
dynamic-BGP Site-to-Site VPN foundation, but its tunnels were down and no usable
routes were accepted. No Terraform plan/apply or AWS mutation occurred, and no
production or clinical connectivity is claimed.

Do not reinterpret a closed wave as incomplete unless current evidence shows
an actual defect or drift.

---

## Working style

Work incrementally.

Before modifying infrastructure code:

1. Inspect the relevant existing files.
2. Identify dependencies and security implications.
3. Prefer the smallest change that satisfies the mission.
4. Run formatting and validation after modifications.
5. Run a Terraform plan before recommending any apply.
6. Report security issues, misconfigurations, excessive permissions,
   unexpected public exposure, missing encryption, logging gaps, or
   destructive changes immediately.

Do not hide or silently remediate security findings.

---

## Actions allowed without additional project-owner approval

Codex may:

- Read repository files.
- Create or modify files inside this repository.
- Create Terraform modules.
- Create Lambda/application source code.
- Create validation and testing scripts.
- Create documentation and sanitized evidence.
- Run terraform fmt.
- Run terraform fmt -check.
- Run terraform validate.
- Run terraform plan.
- Run terraform show on newly generated plans.
- Run non-destructive local tests.
- Run Git status.
- Run Git diff.
- Run Git diff --cached.
- Inspect repository history.
- Run read-only AWS CLI commands when specifically required for verification.
- Analyze logs and configuration.
- Recommend remediation.

---

## Explicit approval required

Stop and request approval before any of the following:

- terraform apply
- terraform destroy
- terraform import
- terraform state rm
- terraform state mv
- terraform state push
- any other Terraform state mutation
- AWS create/update/delete operations outside a reviewed Terraform apply
- IAM privilege expansion
- security-group rule relaxation
- network route changes
- DNS cutover
- production database migration
- AWS DMS production cutover
- production data movement
- source-system shutdown or decommission
- backup deletion
- KMS key deletion or destructive key changes
- disabling CloudTrail, Config, GuardDuty, Security Hub, Inspector, logging,
  encryption, backup, or monitoring controls
- git push
- git merge
- deleting Git branches
- force push
- publishing files to GitHub

Never interpret silence as approval.

---

## Terraform safety rules

Never run terraform apply automatically.

Before an apply recommendation:

1. terraform fmt -check
2. terraform validate
3. terraform plan -detailed-exitcode
4. Inspect the complete resource-change set.
5. Explicitly identify:
   - creates
   - updates
   - destroys
   - replacements
   - IAM changes
   - network/security changes
   - state-address changes

A destroy or replacement affecting a clinic resource must be highlighted
before approval is requested.

Preserve lifecycle prevent_destroy protections unless the project owner
explicitly approves their removal.

---

## Security rules

Treat this as a healthcare-security project.

Apply these principles:

- least privilege
- private-by-default networking
- encryption at rest and in transit
- no routine inbound SSH/RDP
- Session Manager where appropriate
- centralized logging
- traceable administrative actions
- explicit recovery paths
- no public clinical database access
- no credentials in source code
- no credentials in Git
- no secrets in evidence
- masked/synthetic non-production data by default

Never place PHI, PII, credentials, secret keys, passwords, tokens,
private certificates, Terraform state, or binary Terraform plans in Git.

Do not open or reproduce secret-bearing files unless they are required for
the task.

---

## Local sensitive files

Treat the following as local/sensitive:

- terraform.tfvars
- *.tfstate
- *.tfstate.*
- *.tfplan
- .terraform/
- AWS credential/config material
- private keys
- secrets
- private archives

`terraform.tfvars.example` files are documentation templates and may be
tracked only when they contain placeholders or nonsensitive examples.

---

## AWS execution rules

Prefer read-only AWS inspection before proposing any change.

For AWS CLI commands, distinguish clearly between:

- READ-ONLY
- MUTATING

Do not execute mutating AWS commands without explicit approval.

The presence of an authenticated AWS profile does not authorize resource
changes.

---

## Wave 3 closed state

Wave 3 is the Appointment API Workflow. Its engineering is closed with final
deployment intentionally deferred. Thirty Terraform-managed Wave 3 resources
exist; the reviewed remaining 21 non-IAM resources do not exist. Do not claim
full deployment, production readiness, operational acceptance, or clinical
integration.

Expected architecture direction:

Vercel
  -> AWS WAF
  -> API Gateway
  -> Lambda
  -> controlled appointment workflow

Core Wave 3 controls include:

- no direct public clinical-database exposure
- AWS WAF protections
- throttling
- request-size limits
- schema validation
- logging
- HMAC-signed server requests
- timestamp validation
- nonce/replay protection
- idempotency
- data minimization
- controlled exception handling
- request reconciliation
- CloudWatch monitoring
- failure/downtime fallback

Do not start production deployment merely because the Terraform code validates.

---

## Permanent Wave 4 and Wave 5 non-deployment rule

Wave 4 and Wave 5 are permanently limited to design, security, and migration
validation. They may use local Terraform design, formatting, validation,
static/security tests, read-only AWS discovery, architecture and migration
documentation, rollback and backup/restore design, cost analysis, and
portfolio evidence.

For Wave 4 and Wave 5, never:

- run `terraform apply`;
- create or modify AWS resources;
- create EC2, RDS, DMS, IAM roles, security groups, NAT gateways, or endpoints;
- provision secrets;
- perform a live database migration or cutover;
- run destructive testing; or
- request deployment approval or create a deployment gate.

Any Wave 4 or Wave 5 Terraform plan is design validation only and must never be
saved or represented as deployment authorization.

---

## Evidence

Evidence must describe what was actually tested.

Do not claim that a resource, control, test, migration, or recovery path
passed unless there is supporting evidence.

Prefer JSON, Markdown, command output, or sanitized configuration evidence.

Do not create unnecessary .txt evidence files.

---

## Git

Before staging or publishing:

- review git status
- review git diff
- scan for sensitive files
- confirm terraform.tfvars/state/plans are not staged

Do not run git push or merge without explicit approval.
