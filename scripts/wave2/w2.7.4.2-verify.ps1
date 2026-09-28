$Expected = @(
    "aws_vpc.clinic_nonprod",
    "aws_subnet.public_a",
    "aws_subnet.public_b",
    "aws_subnet.private_a",
    "aws_subnet.private_b",
    "aws_internet_gateway.clinic_nonprod",
    "aws_route_table.public",
    "aws_route_table.private_a",
    "aws_route_table.private_b",
    "aws_route.public_internet",
    "aws_route_table_association.public_a",
    "aws_route_table_association.public_b",
    "aws_route_table_association.private_a",
    "aws_route_table_association.private_b",
    "aws_security_group.clinic_nonprod",
    "aws_default_security_group.clinic_nonprod",
    "aws_vpc_security_group_egress_rule.clinic_to_directory",
    "aws_vpc_endpoint.s3_gateway"
)

$State = @(terraform state list)

$Missing = @(
    $Expected | Where-Object { $_ -notin $State }
)

Write-Host ""
Write-Host "Expected network resources: $($Expected.Count)"
Write-Host "Found in state:             $(($Expected | Where-Object { $_ -in $State }).Count)"
Write-Host "Missing:                    $($Missing.Count)"

if ($Missing.Count -gt 0) {
    Write-Host ""
    Write-Host "MISSING RESOURCES:"
    $Missing | ForEach-Object { Write-Host " - $_" }
    throw "W2.7.4 mapping verification FAILED."
}

Write-Host ""
Write-Host "W2.7.4 source-address verification: PASS"