$ModuleFile = "C:\Users\hehek\Desktop\clinic-cloud-iac\modules\network\main.tf"

$ExpectedModuleResources = @(
    'resource "aws_vpc" "clinic_nonprod"',
    'resource "aws_subnet" "public_a"',
    'resource "aws_subnet" "public_b"',
    'resource "aws_subnet" "private_a"',
    'resource "aws_subnet" "private_b"',
    'resource "aws_internet_gateway" "clinic_nonprod"',
    'resource "aws_route_table" "public"',
    'resource "aws_route_table" "private_a"',
    'resource "aws_route_table" "private_b"',
    'resource "aws_route" "public_internet"',
    'resource "aws_route_table_association" "public_a"',
    'resource "aws_route_table_association" "public_b"',
    'resource "aws_route_table_association" "private_a"',
    'resource "aws_route_table_association" "private_b"',
    'resource "aws_security_group" "clinic_nonprod"',
    'resource "aws_default_security_group" "clinic_nonprod"',
    'resource "aws_vpc_security_group_egress_rule" "clinic_to_directory"',
    'resource "aws_vpc_endpoint" "s3_gateway"'
)

$ModuleText = Get-Content $ModuleFile -Raw

$MissingModuleResources = @(
    $ExpectedModuleResources |
    Where-Object { -not $ModuleText.Contains($_) }
)

Write-Host ""
Write-Host "Expected module resources: $($ExpectedModuleResources.Count)"
Write-Host "Found in module:           $($ExpectedModuleResources.Count - $MissingModuleResources.Count)"
Write-Host "Missing:                   $($MissingModuleResources.Count)"

if ($MissingModuleResources.Count -gt 0) {
    Write-Host ""
    $MissingModuleResources | ForEach-Object {
        Write-Host " - $_"
    }

    throw "W2.7.4 destination verification FAILED."
}

Write-Host ""
Write-Host "W2.7.4 destination-address verification: PASS"