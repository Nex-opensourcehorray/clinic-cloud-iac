# Clinic/EMR Terraform design-validation root

This isolated root validates the reusable Clinic/EMR module without connecting
it to active nonproduction state. Identifiers are documentation placeholders;
the root has no backend, tfvars, state, saved plan, credential, or secret value.

Permanent status: **DESIGN VALIDATED — NOT DEPLOYED**. **NEVER DEPLOY** this
Wave 5 package.

Permitted commands are `terraform fmt`, `terraform init -backend=false`, and
`terraform validate`. A plan is unnecessary for this closeout and must never be
saved as deployment authorization. `terraform apply` is permanently prohibited
for Wave 5.
