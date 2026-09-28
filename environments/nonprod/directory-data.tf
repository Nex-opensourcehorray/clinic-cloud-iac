# External AWS Directory Service security group.
# This resource is not owned by the reusable network module.

data "aws_security_group" "directory_controllers" {
  id = var.directory_controller_security_group_id
}
