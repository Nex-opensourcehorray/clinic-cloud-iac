resource "aws_db_subnet_group" "database" {
  name       = "${local.name_prefix}-db"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-db-subnets" })
}

resource "aws_db_parameter_group" "database" {
  name   = "${local.name_prefix}-mysql"
  family = var.database_parameter_group_family

  parameter {
    name  = "require_secure_transport"
    value = "1"
  }

  tags = local.common_tags
}

resource "aws_db_instance" "database" {
  identifier = "${local.name_prefix}-mysql"

  engine         = "mysql"
  engine_version = var.database_engine_version
  instance_class = var.database_instance_class
  db_name        = var.database_name

  allocated_storage     = var.database_allocated_storage_gib
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  username            = var.database_master_username
  password_wo         = var.database_master_password_wo
  password_wo_version = var.database_master_password_wo_version
  port                = 3306

  db_subnet_group_name   = aws_db_subnet_group.database.name
  parameter_group_name   = aws_db_parameter_group.database.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = var.database_backup_retention_days
  backup_window           = "17:00-18:00"
  maintenance_window      = "sun:18:00-sun:19:00"

  auto_minor_version_upgrade      = true
  apply_immediately               = false
  copy_tags_to_snapshot           = true
  deletion_protection             = true
  enabled_cloudwatch_logs_exports = ["error"]
  final_snapshot_identifier       = "${local.name_prefix}-mysql-final"
  skip_final_snapshot             = false

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-mysql" })

  lifecycle {
    prevent_destroy = true
  }
}
