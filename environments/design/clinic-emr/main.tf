# DESIGN VALIDATION ONLY — NEVER DEPLOY.
# Placeholder identifiers model interfaces without reading or changing AWS.

module "clinic_emr" {
  source = "../../../modules/clinic-emr"

  resource_name_prefix = "clinic-nonprod-clinic-emr"
  vpc_id               = "vpc-0123456789abcdef0"
  private_subnet_ids = [
    "subnet-0123456789abcdef0",
    "subnet-0fedcba9876543210",
  ]
  dns_resolver_cidr = "10.0.0.2/32"

  application_ami_id                = "ami-0123456789abcdef0"
  application_instance_profile_name = "clinic-nonprod-clinic-emr-app"
  application_role_arn              = "arn:aws:iam::111122223333:role/clinic-nonprod-clinic-emr-app"

  source_database_cidrs   = ["10.20.0.10/32"]
  integration_https_cidrs = []

  database_master_password_wo         = var.database_master_password_wo
  database_master_password_wo_version = 1
  database_credentials_secret_arn     = "arn:aws:secretsmanager:ap-east-1:111122223333:secret:clinic-nonprod-clinic-emr/database-example"

  dms_source_secret_arn       = "arn:aws:secretsmanager:ap-east-1:111122223333:secret:clinic-nonprod-clinic-emr/dms-source-example"
  dms_target_secret_arn       = "arn:aws:secretsmanager:ap-east-1:111122223333:secret:clinic-nonprod-clinic-emr/dms-target-example"
  dms_secrets_access_role_arn = "arn:aws:iam::111122223333:role/clinic-nonprod-clinic-emr-dms-secrets"
  dms_source_certificate_arn  = "arn:aws:dms:ap-east-1:111122223333:cert:clinic-emr-source-example"
  dms_target_certificate_arn  = "arn:aws:dms:ap-east-1:111122223333:cert:clinic-emr-target-example"

  kms_key_arn             = "arn:aws:kms:ap-east-1:111122223333:key/11111111-2222-3333-4444-555555555555"
  backup_service_role_arn = "arn:aws:iam::111122223333:role/clinic-nonprod-clinic-emr-backup"
  alarm_topic_arn         = "arn:aws:sns:ap-east-1:111122223333:clinic-nonprod-clinic-emr-alerts"

  service_endpoint_security_group_id = null
  existing_fsx_security_group_id     = null
  existing_fsx_arn                   = null

  common_tags = {
    CostCenter         = "CC-CLINIC-MIG-2026"
    DataClassification = "restricted-clinical"
    Environment        = "nonprod"
    Owner              = "IT-Administrator"
    Project            = "clinic"
    System             = "clinic-emr"
  }
}
