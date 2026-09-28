provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = var.offline_validation
  skip_metadata_api_check     = var.offline_validation
  skip_requesting_account_id  = var.offline_validation
}
