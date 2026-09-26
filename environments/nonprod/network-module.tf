module "network" {
  source = "../../modules/network"

  aws_region     = data.aws_region.current.region
  aws_account_id = data.aws_caller_identity.current.account_id

  directory_controller_security_group_id = data.aws_security_group.directory_controllers.id

  vpc_cidr = "10.0.0.0/16"

  public_subnet_a_cidr = "10.0.0.0/20"
  public_subnet_b_cidr = "10.0.16.0/20"

  private_subnet_a_cidr = "10.0.128.0/20"
  private_subnet_b_cidr = "10.0.144.0/20"

  availability_zone_a = "ap-east-1a"
  availability_zone_b = "ap-east-1b"

  resource_name_prefix = "clinic-nonproduction"

  clinic_security_group_name        = "Clinic-NonProd-Group"
  clinic_security_group_description = "Proceed SMB to the Private Group."

  base_tags = {
    BackupPolicy       = "none-approved"
    CostCenter         = "CC-CLINIC-MIG-2026"
    DataClassification = "internal"
    Environment        = "nonprod"
    Owner              = "IT-Administrator"
    System             = "shared-platform"
  }
}