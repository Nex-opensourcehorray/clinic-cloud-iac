# Clinic Cloud IaC

Terraform Infrastructure as Code (IaC) project for the **synthetic clinic AWS migration and cloud security engineering portfolio**.

This repository demonstrates a security-led AWS migration program across six
portfolio waves, from Terraform foundations through a terminated hybrid
integration discovery. Deployment, design-only, deferred, and terminated work
are labeled separately so the repository does not imply production readiness.

> **Data classification:** This portfolio uses synthetic/mock clinic data only. It is not a production clinical environment and does not contain real PHI/PII.

---

## Current Project Status

| Wave | Topic | Status |
|---|---|---|
| Wave 0 | Project foundation | CLOSED |
| Wave 1 | Terraform and IaC foundations | CLOSED |
| Wave 2 | Network foundation | CLOSED — PASS |
| Wave 3 | Appointment API Workflow | ENGINEERING CLOSED — DEPLOYMENT DEFERRED |
| Wave 4 | Pharmacy migration | DESIGN VALIDATED — NOT DEPLOYED |
| Wave 5 | Clinic/EMR shared MySQL migration | DESIGN VALIDATED — NOT DEPLOYED |
| Wave 6 | Lab/Radiology hybrid integration | TERMINATED — EXTERNAL CONNECTIVITY PREREQUISITE UNAVAILABLE |

Wave 3 checkpoints:

- **W3.0 Agentic Workspace & Readiness — CLOSED — PASS**
- **W3.1 Appointment API Architecture & Security Discovery — CLOSED — PASS**
- **W3.2 Appointment API Foundation — CLOSED — PASS**
- **W3.3 HMAC Authentication, Replay Protection, and Atomic Idempotency — CLOSED — PASS**
- **W3.4 WAF & Public API Abuse Hardening — CLOSED — PASS**
- **W3.5 Workflow, Exception & Reconciliation — CLOSED — PASS**
- **W3.6 Monitoring, Alert Routing, and Operational Observability — CLOSED — PASS**
- **W3.7 Security, Negative, Abuse, and Failure-Path Validation — CLOSED — PASS**
- **W3.8 Deployment Readiness & Live Validation Gate — CLOSED — DEPLOYMENT DEFERRED**

Wave 3 is **ENGINEERING CLOSED — DEPLOYMENT DEFERRED**. Its security and
Terraform architectures, adversarial validation, and 205-test suite are
complete. Thirty Wave 3 Terraform-managed resources exist; the final reviewed
21-resource non-IAM remainder was intentionally not deployed. Four execution
roles, two permissions boundaries, and the empty HMAC secret container are
externally governed. The owner retained the IAM administrative boundary, and
no broad IAM workaround was accepted. Wave 3 is not fully deployed,
operationally accepted, production ready, or clinically integrated.

Waves 4 and 5 are permanent design/security/migration-validation exercises.
They may include local Terraform design, static tests, documentation, and
read-only discovery, but they must never create or modify AWS resources and
must never request deployment approval.

Wave 4 is **DESIGN VALIDATED — NOT DEPLOYED**. Its reusable Pharmacy design
models a private Windows EC2 application tier, private RDS for SQL Server,
narrow security-group flows, externally governed identity and secrets,
monitoring, backup, provider-integration alternatives, and a synthetic
migration validation path. Terraform validation and 19 static design tests
passed. No AWS resource, live workload, data migration, or deployment was
created or performed. Evidence is recorded in
`environments/nonprod/evidence/W4/W4_W4-A_20260928_Pharmacy-Design-Validation.json`.

Wave 5 is **DESIGN VALIDATED — NOT DEPLOYED**. Its isolated Terraform and
portfolio documentation model the shared Clinic/EMR migration as private
application compute, private RDS MySQL, and a temporary private DMS full-load
plus CDC path. The package includes data classification, clinical RBAC/UAT,
integrity and CDC validation, FSx consistency, backup/restore, cutover,
rollback, threat analysis, and cost design. Thirty-four static design tests and
Terraform validation passed. No AWS resource, database migration, clinical UAT,
cutover, or rollback was performed. Evidence is recorded in
`environments/nonprod/evidence/W5/W5_W5-A_20260928_Clinic-EMR-Design-Validation.json`.

Wave 6 is **DISCOVERY CLOSED — IMPLEMENTATION TERMINATED**. The work remained
read-only. Authenticated AWS discovery confirmed an existing VGW-based,
dynamic-BGP Site-to-Site VPN foundation, but both tunnels were down, no routes
were accepted, and the private route tables had neither VGW propagation nor
explicit on-premises routes. Existing-VPN reuse was therefore classified as
conditional rather than ready.

Directory Service and FSx remained private-only and were not exposed through a
working hybrid path. Exact Lab/Radiology endpoint CIDRs, protocols, and routing
requirements remained vendor inputs, while the required external ISP
connectivity prerequisite was unavailable. No Terraform plan or apply was run,
no AWS resource was created or modified, and no production or clinical
connectivity was claimed.

---

## Wave 1 Objectives

Wave 1 establishes the Terraform and IaC foundation required for later migration waves.

The main objectives are to understand and demonstrate:

- Terraform CLI workflow
- AWS provider configuration
- AWS IAM Identity Center / SSO authentication
- variables and locals
- data sources
- Terraform resource references
- implicit dependency relationships
- local state behavior
- Terraform state security
- resource import
- lifecycle ownership
- controlled create/update operations
- configuration drift detection
- drift reconciliation
- remote S3 state
- S3 state versioning
- native S3 state locking
- repository hygiene
- source-control safety
- repeatable plan/review/apply workflows

---

## Repository Structure

```text
clinic-cloud-iac/
├── .codex/
├── .github/
│   └── workflows/
├── application/
│   ├── appointment-api/
│   ├── pharmacy/
│   └── clinic-emr/
├── bootstrap/
│   └── state-backend/
├── docs/
│   ├── mission-2-security/
│   └── portfolio-closeout/
├── environments/
│   ├── design/
│   │   ├── pharmacy/
│   │   └── clinic-emr/
│   └── nonprod/
├── modules/
│   ├── network/
│   ├── appointment-api/
│   ├── pharmacy/
│   └── clinic-emr/
├── scripts/
├── AGENTS.md
├── README.md
├── .gitattributes
└── .gitignore
```

Local `terraform.tfvars`, backend configuration, Terraform state, saved plans,
working directories, and generated Lambda packages are intentionally excluded.

### Terraform Roots

The repository contains four Terraform roots with separate purposes and safety
boundaries.

#### `bootstrap/state-backend`

Creates and protects the S3 backend used by the NonProduction Terraform environment.

This root currently keeps its own bootstrap state locally.

#### `environments/nonprod`

Contains the active NonProduction configuration for Waves 1 and 2 and the
applicable Terraform-managed portion of Wave 3.

Its state has been migrated from local state to the secured S3 remote backend.
The public repository keeps only an empty backend declaration; private backend
values are supplied from an untracked file based on `backend.hcl.example`.

#### `environments/design/pharmacy`

Wave 4 validation-only root. It has no remote backend and is permanently
classified **NEVER DEPLOY**.

#### `environments/design/clinic-emr`

Wave 5 validation-only root. It has no remote backend and is permanently
classified **NEVER DEPLOY**.

---

## AWS Environment

Current Wave 1 environment:

```text
Environment:       Clinic NonProduction
Primary Region:    ap-east-1
Authentication:    AWS IAM Identity Center / SSO
Terraform:         1.15.x
AWS Provider:      6.x
```

Authentication is performed using temporary SSO credentials.

No long-lived AWS access key or secret key is stored in Terraform source code.

Typical local profile selection:

```powershell
$env:AWS_PROFILE="<AWS_PROFILE>"
aws sso login --profile <AWS_PROFILE>
aws sts get-caller-identity
```

The local AWS profile name is workstation configuration and is intentionally not hard-coded into the Terraform provider.

---

## Terraform Workflow

The standard workflow used by this project is:

```text
terraform fmt
      ↓
terraform validate
      ↓
terraform plan -out=<plan-file>
      ↓
review the saved plan
      ↓
terraform show <plan-file>
      ↓
terraform apply <plan-file>
      ↓
verify AWS independently
      ↓
terraform plan
      ↓
expect No changes
```

### Why Saved Plans Are Used

A saved plan helps ensure that the exact Terraform proposal reviewed by the engineer is the proposal later executed.

```powershell
terraform plan -out=change.tfplan
terraform show change.tfplan
terraform apply change.tfplan
```

Saved `.tfplan` files are temporary artifacts and must not be committed to source control.

---

## Terraform Configuration Model

### Variable

A variable receives input from outside the module.

```hcl
variable "environment" {
  type = string
}
```

Reference:

```hcl
var.environment
```

### Local

A local is an internally derived or reusable value.

```hcl
locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
```

Reference:

```hcl
local.name_prefix
```

### Data Source

A data source reads an existing object without taking lifecycle ownership.

```hcl
data "aws_vpc" "clinic_nonprod" {
  filter {
    name   = "tag:Name"
    values = ["clinic-nonproduction-vpc"]
  }
}
```

Reference:

```hcl
data.aws_vpc.clinic_nonprod.id
```

### Resource

A resource declares infrastructure that Terraform manages through its lifecycle.

```hcl
resource "aws_ssm_parameter" "wave1_training" {
  name  = var.training_parameter_name
  type  = "String"
  value = var.training_parameter_value

  tags = local.common_tags
}
```

Reference:

```hcl
aws_ssm_parameter.wave1_training.arn
```

---

## Terraform State

Terraform state records Terraform's understanding of managed infrastructure.

```text
Terraform configuration
        ↓
Terraform state
        ↓
AWS provider
        ↓
AWS resources
```

State may record:

- Terraform resource addresses
- AWS object identifiers
- provider-derived attributes
- outputs
- dependency-related information
- potentially sensitive values

### Security Rule

Terraform state must be treated as security-sensitive.

Do not:

- commit `.tfstate` files to Git
- upload state files to public repositories
- email state files
- include state files in portfolio uploads
- assume `sensitive = true` means a value is absent from state

---

## Import and Lifecycle Ownership

Wave 1 demonstrated the difference between reading an existing AWS resource and importing it into Terraform lifecycle ownership.

Before import:

```text
Configuration:
aws_vpc.clinic_nonprod_import_lab exists

State:
no object mapped to that resource address

Terraform result:
+ CREATE
```

After import:

```text
Terraform address
aws_vpc.clinic_nonprod_import_lab

        ↕

Existing AWS VPC
```

Terraform can then compare the imported resource against the declared resource configuration and propose updates, replacements, or destruction if the configuration does not match.

`terraform state rm` removes the Terraform ownership mapping from state. It does **not** delete the AWS resource.

---

## First Terraform-Managed AWS Resource

Wave 1 created a low-risk SSM Parameter Store training resource:

```text
/clinic/nonprod/iac/wave1/owner
```

Resource type:

```text
String
```

Training value:

```text
terraform-training
```

This parameter exists only to demonstrate the Terraform lifecycle.

It is not a secret and does not contain production or clinical data.

---

## Configuration Drift

Wave 1 deliberately created and repaired configuration drift.

Desired Terraform value:

```text
terraform-training
```

Manual out-of-band AWS change:

```text
manual-drift-test
```

Terraform detected the mismatch and proposed an in-place update.

Final result after reconciliation:

```text
No changes.
Your infrastructure matches the configuration.
```

Terraform configuration represents the **desired state**. AWS provides the **observed state**. `terraform plan` calculates the actions required to reconcile the observed state with the desired state.

---

## Remote State Backend

The NonProduction Terraform environment now uses an Amazon S3 remote backend.

Backend object path:

```text
environments/nonprod/terraform.tfstate
```

The S3 backend was created by the separate `bootstrap/state-backend` Terraform root module.

### State Backend Controls

The backend includes:

- S3 bucket versioning
- default server-side encryption
- Block Public Access
- BucketOwnerEnforced object ownership
- TLS-only access policy
- `force_destroy = false`
- Terraform `prevent_destroy`
- native S3 state locking

### Encryption

The current Wave 1 backend uses:

```text
SSE-S3 / AES256
```

This is the current pilot baseline.

A customer-managed KMS key may be considered in later hardening work if required.

---

## State Migration

The NonProduction environment state was migrated from the local backend to S3 using:

```powershell
terraform init -migrate-state
```

The migration changed **where Terraform stores state**.

It did not change:

- Terraform resource addresses
- Terraform lifecycle ownership
- the SSM parameter itself
- the AWS VPC
- the desired Terraform configuration

---

## Native S3 State Locking

The backend uses:

```hcl
use_lockfile = true
```

State locking was validated with two concurrent Terraform consoles.

Observed behavior:

```text
Console A
acquired state lock
        ↓

Console B
attempted terraform plan
        ↓
state lock acquisition failed
        ↓
concurrent write prevented
```

After Console A released the lock normally, Console B successfully acquired the lock and completed a clean plan.

---

## Source-Control Hygiene

Commit-worthy files normally include:

```text
*.tf
.terraform.lock.hcl
README.md
.gitignore
terraform.tfvars.example
backend.hcl.example
documentation files
```

Do not commit:

```text
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
terraform.tfvars
*.tfvars
backend.hcl
credentials
private keys
VPN PSKs
session tokens
```

Suggested `.gitignore`:

```gitignore
# Terraform working directories
**/.terraform/*

# Terraform local state and backups
*.tfstate
*.tfstate.*

# Saved Terraform plans
*.tfplan

# Environment-specific variable values
*.tfvars
*.tfvars.json

# Crash logs
crash.log
crash.*.log

# Override files
override.tf
override.tf.json
*_override.tf
*_override.tf.json

# Terraform CLI configuration
.terraformrc
terraform.rc

# OS/editor noise
.DS_Store
Thumbs.db
```

---

## Security Principles Used in Wave 1

Wave 1 applies the following security practices:

- SSO temporary credentials instead of hard-coded static credentials
- no credentials in `providers.tf`
- Terraform state treated as sensitive
- S3 Block Public Access on the state bucket
- S3 state encryption
- S3 versioning
- TLS-only bucket access
- BucketOwnerEnforced ownership
- native state locking
- plan-before-apply change control
- independent AWS verification after apply
- no real PHI/PII
- no production clinical claims
- no secret values used in the training SSM parameter

---

## Infrastructure Classification

### Deployed and Terraform-managed

The separately bootstrapped backend manages the S3 state-storage controls. The
NonProduction root has evidenced lifecycle ownership for the Wave 1 training
parameter and the Wave 2 network foundation: VPC, public/private subnets,
Internet Gateway, route tables and associations, security-group controls, and
their relationships.

Wave 3 evidence confirms 30 Terraform-managed Appointment API resources exist.
This is a partial deployment only; it is not production ready, operationally
accepted, or clinically integrated.

### Deployment deferred

Wave 3 engineering is closed with deployment deferred. The reviewed remaining
21 non-IAM resources were intentionally not deployed. No future apply is
authorized by this repository state.

### Design-only and never deployed

Wave 4 Pharmacy and Wave 5 Clinic/EMR are validation-only designs with isolated
local roots and no backend. They model EC2, RDS, DMS, networking, monitoring,
backup, and migration controls, but created no AWS resources and moved no data.

### Externally managed dependencies

External ownership applies where documented to IAM roles and permission
boundaries, Secrets Manager containers, KMS contracts, Directory Service, FSx,
and related owner-controlled dependencies. Terraform data sources or input
contracts do not imply lifecycle ownership.

### Terminated

Wave 6 Lab/Radiology hybrid implementation was terminated after read-only
discovery because the external connectivity prerequisite was unavailable. No
Terraform plan/apply or AWS mutation occurred.

---

## Wave 1 Validation Results

Evidence collected during Wave 1 demonstrated:

```text
Terraform fmt                         ✅
Terraform validate                    ✅
Provider authentication               ✅
NonProd VPC data-source discovery     ✅
Local state creation                  ✅
Saved-plan workflow                   ✅
Resource import                       ✅
State ownership removal               ✅
First managed resource creation       ✅
Controlled in-place update            ✅
Configuration drift detection         ✅
Drift reconciliation                  ✅
S3 backend bootstrap                  ✅
State versioning                      ✅
State encryption                      ✅
Public access blocking                ✅
TLS-only policy                       ✅
State migration                       ✅
Remote-state read/write               ✅
Native state locking                  ✅
Competing state writer blocked        ✅
Post-lock plan                        ✅
```

W1.8 final closure checks additionally verify:

- recursive formatting
- both root modules validate
- both root modules produce zero-drift plans
- Git ignore behavior
- removal of temporary plan artifacts
- no committed state files
- basic secret hygiene

---

## Retained Wave 1 Observation

### W1-O01 — Bootstrap State

The backend bootstrap root currently uses protected local Terraform state.

```text
bootstrap/state-backend
        ↓
local bootstrap terraform.tfstate
```

This is an intentional bootstrap design for Wave 1.

The NonProduction environment state has already been migrated to the secured S3 backend.

Future waves may revisit the bootstrap-state operating model if a stronger team-oriented architecture is required.

This observation does not block Wave 1 closure.

---

## Wave 1 Learning Outcomes

By the end of Wave 1, the engineer should be able to explain:

1. The difference between `terraform validate`, `plan`, and `apply`.
2. Why provider credentials must not be hard-coded.
3. The difference between variables and locals.
4. The difference between data sources and resources.
5. How Terraform references create implicit dependencies.
6. Why Terraform needs state.
7. Why Terraform state must be protected.
8. The difference between `.terraform.lock.hcl` and `.tfstate`.
9. Why an existing AWS object is not automatically Terraform-managed.
10. What `terraform import` changes.
11. The difference between `terraform state rm` and destroy.
12. How Terraform creates and updates managed resources.
13. How Terraform detects configuration drift.
14. Why Terraform configuration represents desired state.
15. Why remote state is preferable for team workflows.
16. How S3 versioning protects state history.
17. Why state locking matters.
18. Why a bootstrap state boundary exists.
19. Which Terraform artifacts belong in Git.
20. Which Terraform artifacts must remain private.

---

## Wave 1 Closure Result

```text
W1.1  Terraform foundation                 ✅
W1.2  Variables / locals / discovery       ✅
W1.3  State fundamentals                   ✅
W1.4  Import / lifecycle ownership         ✅
W1.5  First managed resource               ✅
W1.6  Drift / reconciliation               ✅
W1.7  Remote state / locking               ✅
W1.8  Repository / security review         ✅

Final result:

WAVE 1
✅ PASS — TERRAFORM & IaC FOUNDATION COMPLETE
```

---

## Engineering Workflow

The portfolio waves are closed, deferred, design-only, or terminated as stated
above. This workflow remains the governing pattern for any separately approved
future work; it does not reopen Wave 6 or authorize deployment.

The same core workflow remains:

```text
requirement
   ↓
architecture
   ↓
Terraform design
   ↓
code
   ↓
fmt / validate
   ↓
plan
   ↓
security review
   ↓
approved apply
   ↓
independent verification
   ↓
evidence
```

---

## Disclaimer

This repository is a learning and portfolio environment.

It does not represent production clinical authorization, healthcare compliance certification, or production go-live approval.
