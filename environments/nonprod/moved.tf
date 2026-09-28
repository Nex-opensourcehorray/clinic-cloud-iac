# W2.7.4
# Pending declarative state-address migration.
# DO NOT rename to moved.tf until W2.7.5.

moved {
  from = aws_vpc.clinic_nonprod
  to   = module.network.aws_vpc.clinic_nonprod
}

moved {
  from = aws_subnet.public_a
  to   = module.network.aws_subnet.public_a
}

moved {
  from = aws_subnet.public_b
  to   = module.network.aws_subnet.public_b
}

moved {
  from = aws_subnet.private_a
  to   = module.network.aws_subnet.private_a
}

moved {
  from = aws_subnet.private_b
  to   = module.network.aws_subnet.private_b
}

moved {
  from = aws_internet_gateway.clinic_nonprod
  to   = module.network.aws_internet_gateway.clinic_nonprod
}

moved {
  from = aws_route_table.public
  to   = module.network.aws_route_table.public
}

moved {
  from = aws_route_table.private_a
  to   = module.network.aws_route_table.private_a
}

moved {
  from = aws_route_table.private_b
  to   = module.network.aws_route_table.private_b
}

moved {
  from = aws_route.public_internet
  to   = module.network.aws_route.public_internet
}

moved {
  from = aws_route_table_association.public_a
  to   = module.network.aws_route_table_association.public_a
}

moved {
  from = aws_route_table_association.public_b
  to   = module.network.aws_route_table_association.public_b
}

moved {
  from = aws_route_table_association.private_a
  to   = module.network.aws_route_table_association.private_a
}

moved {
  from = aws_route_table_association.private_b
  to   = module.network.aws_route_table_association.private_b
}

moved {
  from = aws_security_group.clinic_nonprod
  to   = module.network.aws_security_group.clinic_nonprod
}

moved {
  from = aws_default_security_group.clinic_nonprod
  to   = module.network.aws_default_security_group.clinic_nonprod
}

moved {
  from = aws_vpc_security_group_egress_rule.clinic_to_directory
  to   = module.network.aws_vpc_security_group_egress_rule.clinic_to_directory
}

moved {
  from = aws_vpc_endpoint.s3_gateway
  to   = module.network.aws_vpc_endpoint.s3_gateway
}