resource "aws_security_group" "application" {
  name        = "${local.name_prefix}-app"
  description = "Private Clinic and EMR application tier; no inbound SSH or RDP"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sg-app" })
}

resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-db"
  description = "Private Clinic and EMR MySQL tier"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sg-db" })
}

resource "aws_security_group" "dms" {
  name        = "${local.name_prefix}-dms"
  description = "Private DMS full-load and CDC replication tier"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-sg-dms" })
}

resource "aws_vpc_security_group_ingress_rule" "database_from_application" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.application.id
  description                  = "MySQL from Clinic and EMR application tier only"
  from_port                    = 3306
  to_port                      = 3306
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_dms" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.dms.id
  description                  = "MySQL from the private DMS replication tier only"
  from_port                    = 3306
  to_port                      = 3306
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_database" {
  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "TLS MySQL to the Clinic and EMR database"
  from_port                    = 3306
  to_port                      = 3306
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "dms_to_target_database" {
  security_group_id            = aws_security_group.dms.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "DMS full-load and CDC to target RDS MySQL"
  from_port                    = 3306
  to_port                      = 3306
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "dms_to_source_database" {
  for_each = toset(var.source_database_cidrs)

  security_group_id = aws_security_group.dms.id
  cidr_ipv4         = each.value
  description       = "DMS full-load and CDC to an exact private source MySQL CIDR"
  from_port         = 3306
  to_port           = 3306
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_integrations" {
  for_each = toset(var.integration_https_cidrs)

  security_group_id = aws_security_group.application.id
  cidr_ipv4         = each.value
  description       = "Contract-approved Clinic and EMR HTTPS integration"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_service_endpoints" {
  count = var.service_endpoint_security_group_id == null ? 0 : 1

  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = var.service_endpoint_security_group_id
  description                  = "HTTPS to externally managed SSM, telemetry, KMS, and secret endpoints"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "dms_to_service_endpoints" {
  count = var.service_endpoint_security_group_id == null ? 0 : 1

  security_group_id            = aws_security_group.dms.id
  referenced_security_group_id = var.service_endpoint_security_group_id
  description                  = "HTTPS to externally managed DMS dependencies"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_to_fsx" {
  count = var.existing_fsx_security_group_id == null ? 0 : 1

  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = var.existing_fsx_security_group_id
  description                  = "SMB to externally managed FSx only when vendor evidence requires it"
  from_port                    = 445
  to_port                      = 445
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application_dns_udp" {
  security_group_id = aws_security_group.application.id
  cidr_ipv4         = var.dns_resolver_cidr
  description       = "DNS to the exact private resolver"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
}

resource "aws_vpc_security_group_egress_rule" "application_dns_tcp" {
  security_group_id = aws_security_group.application.id
  cidr_ipv4         = var.dns_resolver_cidr
  description       = "DNS TCP fallback to the exact private resolver"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "dms_dns_udp" {
  security_group_id = aws_security_group.dms.id
  cidr_ipv4         = var.dns_resolver_cidr
  description       = "DMS DNS to the exact private resolver"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
}

resource "aws_vpc_security_group_egress_rule" "dms_dns_tcp" {
  security_group_id = aws_security_group.dms.id
  cidr_ipv4         = var.dns_resolver_cidr
  description       = "DMS DNS TCP fallback to the exact private resolver"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "tcp"
}
