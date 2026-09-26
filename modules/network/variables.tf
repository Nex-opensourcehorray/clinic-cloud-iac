variable "aws_region" {
  description = "AWS Region used by the network module"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID owning the network resources"
  type        = string
}

variable "directory_controller_security_group_id" {
  description = "Existing Directory Service controller security group ID"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_a_cidr" {
  description = "CIDR block for public subnet A"
  type        = string
}

variable "public_subnet_b_cidr" {
  description = "CIDR block for public subnet B"
  type        = string
}

variable "private_subnet_a_cidr" {
  description = "CIDR block for private subnet A"
  type        = string
}

variable "private_subnet_b_cidr" {
  description = "CIDR block for private subnet B"
  type        = string
}

variable "availability_zone_a" {
  description = "Availability Zone used by subnet A resources"
  type        = string
}

variable "availability_zone_b" {
  description = "Availability Zone used by subnet B resources"
  type        = string
}

variable "resource_name_prefix" {
  description = "Naming prefix used by the existing network resources"
  type        = string
}

variable "clinic_security_group_name" {
  description = "Name of the clinic workload security group"
  type        = string
}

variable "clinic_security_group_description" {
  description = "Description of the clinic workload security group"
  type        = string
}

variable "base_tags" {
  description = "Tags shared by the NonProd network resources"
  type        = map(string)
}