resource "aws_db_subnet_group" "database" {
  name       = "${local.name_prefix}-db"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-db-subnets" })
}

resource "aws_db_instance" "database" {
  identifier = "${local.name_prefix}-sqlserver"

  engine         = "sqlserver-ex"
  license_model  = "license-included"
  instance_class = var.database_instance_class

  allocated_storage     = var.database_allocated_storage_gib
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  username            = var.database_master_username
  password_wo         = var.database_master_password_wo
  password_wo_version = var.database_master_password_wo_version
  port                = 1433

  db_subnet_group_name   = aws_db_subnet_group.database.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = false

  domain               = var.enable_directory_authentication ? var.directory_id : null
  domain_iam_role_name = var.enable_directory_authentication ? var.directory_iam_role_name : null

  backup_retention_period = var.backup_retention_days
  backup_window           = "17:00-18:00"
  maintenance_window      = "sun:18:00-sun:19:00"

  auto_minor_version_upgrade      = true
  apply_immediately               = false
  copy_tags_to_snapshot           = true
  deletion_protection             = true
  enabled_cloudwatch_logs_exports = ["agent", "error"]
  final_snapshot_identifier       = "${local.name_prefix}-sqlserver-final"
  skip_final_snapshot             = false

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sqlserver" })

  lifecycle {
    prevent_destroy = true
  }
}
