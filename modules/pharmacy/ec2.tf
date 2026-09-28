resource "aws_instance" "application" {
  ami                         = var.application_ami_id
  instance_type               = var.application_instance_type
  subnet_id                   = var.private_subnet_ids[0]
  associate_public_ip_address = false
  iam_instance_profile        = var.application_instance_profile_name
  vpc_security_group_ids      = [aws_security_group.application.id]
  monitoring                  = true
  ebs_optimized               = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    encrypted             = true
    kms_key_id            = var.kms_key_arn
    volume_type           = "gp3"
    volume_size           = 50
    delete_on_termination = true
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-app" })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/clinic/nonprod/pharmacy/application"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}
