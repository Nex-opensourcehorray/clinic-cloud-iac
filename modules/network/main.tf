resource "aws_vpc" "clinic_nonprod" {
  cidr_block           = var.vpc_cidr
  instance_tenancy     = "default"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-vpc"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.clinic_nonprod.id
  cidr_block              = var.public_subnet_a_cidr
  availability_zone       = var.availability_zone_a
  map_public_ip_on_launch = false

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-subnet-public1-${var.availability_zone_a}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.clinic_nonprod.id
  cidr_block              = var.public_subnet_b_cidr
  availability_zone       = var.availability_zone_b
  map_public_ip_on_launch = false

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-subnet-public2-${var.availability_zone_b}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "private_a" {
  vpc_id                  = aws_vpc.clinic_nonprod.id
  cidr_block              = var.private_subnet_a_cidr
  availability_zone       = var.availability_zone_a
  map_public_ip_on_launch = false

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-subnet-private1-${var.availability_zone_a}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "private_b" {
  vpc_id                  = aws_vpc.clinic_nonprod.id
  cidr_block              = var.private_subnet_b_cidr
  availability_zone       = var.availability_zone_b
  map_public_ip_on_launch = false

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-subnet-private2-${var.availability_zone_b}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_internet_gateway" "clinic_nonprod" {
  vpc_id = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-igw"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table" "private_a" {
  vpc_id = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-rtb-private1-${var.availability_zone_a}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-rtb-public"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table" "private_b" {
  vpc_id = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
      Name      = "${var.resource_name_prefix}-rtb-private2-${var.availability_zone_b}"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.clinic_nonprod.id

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private_a.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private_b.id
}

resource "aws_security_group" "clinic_nonprod" {
  name        = var.clinic_security_group_name
  description = var.clinic_security_group_description
  vpc_id      = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "manual-exception"
    }
  )
}

resource "aws_vpc_security_group_egress_rule" "clinic_to_directory" {
  security_group_id            = aws_security_group.clinic_nonprod.id
  referenced_security_group_id = var.directory_controller_security_group_id
  ip_protocol                  = "-1"
}

resource "aws_default_security_group" "clinic_nonprod" {
  vpc_id = aws_vpc.clinic_nonprod.id

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "aws-service"
      Name      = "${var.resource_name_prefix}-sg-default"
    }
  )
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = aws_vpc.clinic_nonprod.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [
    aws_route_table.private_a.id,
    aws_route_table.private_b.id
  ]

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid       = "AllowCurrentAccountS3ResourcesOnly"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:*"
        Resource  = "*"

        Condition = {
          StringEquals = {
            "aws:PrincipalAccount" = var.aws_account_id
            "s3:ResourceAccount"   = var.aws_account_id
          }
        }
      }
    ]
  })

  tags = merge(
    var.base_tags,
    {
      ManagedBy = "terraform"
      Name      = "${var.resource_name_prefix}-vpce-s3"
    }
  )
}