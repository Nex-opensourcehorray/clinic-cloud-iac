# DESIGN VALIDATION ONLY — NEVER DEPLOY.
# Placeholder identifiers model interfaces without reading or changing AWS.

module "pharmacy" {
  source = "../../../modules/pharmacy"

  resource_name_prefix = "clinic-nonprod-pharmacy"
  vpc_id               = "vpc-0123456789abcdef0"
  private_subnet_ids = [
    "subnet-0123456789abcdef0",
    "subnet-0fedcba9876543210",
  ]

  application_ami_id                = "ami-0123456789abcdef0"
  application_instance_profile_name = "clinic-nonprod-pharmacy-app"
  application_role_arn              = "arn:aws:iam::111122223333:role/clinic-nonprod-pharmacy-app"

  database_credentials_secret_arn     = "arn:aws:secretsmanager:ap-east-1:111122223333:secret:clinic-nonprod-pharmacy/database-example"
  database_master_password_wo         = var.database_master_password_wo
  database_master_password_wo_version = 1

  kms_key_arn             = "arn:aws:kms:ap-east-1:111122223333:key/11111111-2222-3333-4444-555555555555"
  backup_service_role_arn = "arn:aws:iam::111122223333:role/clinic-nonprod-pharmacy-backup"
  alarm_topic_arn         = "arn:aws:sns:ap-east-1:111122223333:clinic-nonprod-pharmacy-alerts"

  provider_https_cidrs            = []
  ssm_endpoint_security_group_id  = null
  enable_directory_authentication = false

  common_tags = {
    CostCenter         = "CC-CLINIC-MIG-2026"
    DataClassification = "confidential"
    Environment        = "nonprod"
    Owner              = "IT-Administrator"
    Project            = "clinic"
    System             = "pharmacy"
  }
}
