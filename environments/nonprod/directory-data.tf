# External AWS Directory Service security group.
# This resource is not owned by the reusable network module.

data "aws_security_group" "directory_controllers" {
  id = "sg-0f43ac70d383b4859"
}