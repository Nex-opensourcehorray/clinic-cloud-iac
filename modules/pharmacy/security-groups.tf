resource "aws_security_group" "application" {
  name        = "${local.name_prefix}-app"
  description = "Pharmacy application tier; no inbound RDP or public access"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sg-app" })
}

resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-db"
  description = "Pharmacy SQL Server tier; application-SG access only"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sg-db" })
}

resource "aws_vpc_security_group_ingress_rule" "database_from_application" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.application.id
  description                  = "SQL Server from the Pharmacy application tier only"
  from_port                    = 1433
  to_port                      = 1433
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_database" {
  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "SQL Server to the Pharmacy database tier only"
  from_port                    = 1433
  to_port                      = 1433
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_provider_https" {
  for_each = toset(var.provider_https_cidrs)

  security_group_id = aws_security_group.application.id
  cidr_ipv4         = each.value
  description       = "Contract-approved provider or controlled-egress HTTPS"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_ssm_endpoints" {
  count = var.ssm_endpoint_security_group_id == null ? 0 : 1

  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = var.ssm_endpoint_security_group_id
  description                  = "HTTPS to externally managed SSM and telemetry endpoints"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}
