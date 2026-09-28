output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.clinic_nonprod.id
}

output "vpc_cidr" {
  description = "VPC CIDR"
  value       = aws_vpc.clinic_nonprod.cidr_block
}

output "main_route_table_id" {
  description = "AWS-created VPC main/fallback route table ID"
  value       = aws_vpc.clinic_nonprod.main_route_table_id
}

output "subnet_ids" {
  description = "Network subnet IDs"

  value = {
    public_a  = aws_subnet.public_a.id
    public_b  = aws_subnet.public_b.id
    private_a = aws_subnet.private_a.id
    private_b = aws_subnet.private_b.id
  }
}

output "route_table_ids" {
  description = "Route table IDs preserving the current NonProd output order"

  value = [
    aws_route_table.private_a.id,
    aws_route_table.public.id,
    aws_route_table.private_b.id,
    aws_vpc.clinic_nonprod.main_route_table_id,
  ]
}

output "internet_gateway_id" {
  description = "Internet Gateway ID"
  value       = aws_internet_gateway.clinic_nonprod.id
}

output "security_group_ids" {
  description = "Explicit security-group boundaries"

  value = {
    clinic_nonprod        = aws_security_group.clinic_nonprod.id
    default               = aws_default_security_group.clinic_nonprod.id
    directory_controllers = var.directory_controller_security_group_id
  }
}

output "s3_gateway_endpoint_id" {
  description = "S3 Gateway VPC Endpoint ID"
  value       = aws_vpc_endpoint.s3_gateway.id
}