terraform {
  backend "s3" {
    bucket       = "clinic-nonprod-tfstate-97cf210a5d24"
    key          = "environments/nonprod/terraform.tfstate"
    region       = "ap-east-1"
    encrypt      = true
    use_lockfile = true
  }
}