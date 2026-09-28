# Pharmacy Terraform design-validation root

This root exists only to initialize and validate the reusable Pharmacy module
without connecting it to the partially deployed nonproduction environment.
Every identifier is a documented placeholder. No tfvars file, backend, saved
plan, state, credential, or secret value belongs here.

Permanent status: **DESIGN VALIDATED — NOT DEPLOYED**. **NEVER DEPLOY** this
Wave 4 design package.

Permitted commands are `terraform fmt`, `terraform init -backend=false`, and
`terraform validate`. Do not run `terraform plan` unless a later design review
explicitly requires it, never save such a plan, and never run `terraform apply`.
