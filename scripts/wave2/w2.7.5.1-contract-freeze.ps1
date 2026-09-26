$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== W2.7.5.1 MODULE INPUT CONTRACT FREEZE ==="
Write-Host ""

# ------------------------------------------------------------
# Safety checks
# ------------------------------------------------------------

if (Test-Path (Join-Path $PSScriptRoot "moved.tf")) {
    throw "STOP: moved.tf is already active. W2.7.5.1 expects moved.tf.pending only."
}

$PendingMoved = Join-Path $PSScriptRoot "moved.tf.pending"

if (-not (Test-Path $PendingMoved)) {
    throw "STOP: moved.tf.pending is missing."
}

$ModuleMain = Join-Path $PSScriptRoot "..\..\modules\network\main.tf"

if (-not (Test-Path $ModuleMain)) {
    throw "STOP: modules\network\main.tf is missing."
}

# ------------------------------------------------------------
# Confirm the current state still uses root addresses
# ------------------------------------------------------------

$StateAddresses = @(terraform state list)

if ($LASTEXITCODE -ne 0) {
    throw "terraform state list failed."
}

$ModuleStateResources = @(
    $StateAddresses |
    Where-Object { $_ -like "module.network.*" }
)

if ($ModuleStateResources.Count -ne 0) {
    Write-Host ""
    Write-Host "Unexpected module resources already in state:"
    $ModuleStateResources | ForEach-Object {
        Write-Host " - $_"
    }

    throw "STOP: module.network is already represented in state."
}

# ------------------------------------------------------------
# Read the current Terraform state as JSON
# ------------------------------------------------------------

$StateJsonRaw = terraform show -json

if ($LASTEXITCODE -ne 0) {
    throw "terraform show -json failed."
}

$StateJson = $StateJsonRaw | ConvertFrom-Json

$Resources = @(
    $StateJson.values.root_module.resources
)

function Get-StateResource {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address
    )

    $Found = @(
        $Resources |
        Where-Object { $_.address -eq $Address }
    )

    if ($Found.Count -ne 1) {
        throw "Expected exactly one state resource for $Address; found $($Found.Count)."
    }

    return $Found[0]
}

# ------------------------------------------------------------
# Load resources whose exact values become module inputs
# ------------------------------------------------------------

$Vpc = Get-StateResource "aws_vpc.clinic_nonprod"

$PublicA = Get-StateResource "aws_subnet.public_a"
$PublicB = Get-StateResource "aws_subnet.public_b"

$PrivateA = Get-StateResource "aws_subnet.private_a"
$PrivateB = Get-StateResource "aws_subnet.private_b"

$ClinicSg = Get-StateResource "aws_security_group.clinic_nonprod"

# ------------------------------------------------------------
# Ensure the module's two-AZ assumption matches reality
# ------------------------------------------------------------

if ($PublicA.values.availability_zone -ne $PrivateA.values.availability_zone) {
    throw "STOP: public_a and private_a do not use the same AZ."
}

if ($PublicB.values.availability_zone -ne $PrivateB.values.availability_zone) {
    throw "STOP: public_b and private_b do not use the same AZ."
}

# ------------------------------------------------------------
# Derive resource-name prefix from the existing VPC Name tag
# Example:
# clinic-nonproduction-vpc -> clinic-nonproduction
# ------------------------------------------------------------

$VpcName = [string]$Vpc.values.tags.Name

if (-not $VpcName.EndsWith("-vpc")) {
    throw "STOP: Existing VPC Name tag does not end in '-vpc': $VpcName"
}

$ResourceNamePrefix = $VpcName.Substring(
    0,
    $VpcName.Length - 4
)

# ------------------------------------------------------------
# Derive the common tag set.
#
# Name and ManagedBy are deliberately excluded because the
# child module preserves those individually per resource.
# ------------------------------------------------------------

$BaseTags = [ordered]@{}

foreach ($Property in $Vpc.values.tags.PSObject.Properties) {

    if ($Property.Name -notin @(
        "Name",
        "ManagedBy"
    )) {
        $BaseTags[$Property.Name] = [string]$Property.Value
    }
}

# ------------------------------------------------------------
# Build the exact module-input contract
# ------------------------------------------------------------

$Contract = [ordered]@{

    EvidenceId = "W2.7.5.1"

    Purpose = "Freeze exact existing values before network module cutover"

    CurrentState = [ordered]@{
        RootNetworkAddressesPresent = $true
        ModuleNetworkAddressesPresent = $false
        PendingMovedFilePresent = $true
        ActiveMovedFilePresent = $false
    }

    ModuleInputs = [ordered]@{

        vpc_cidr = [string]$Vpc.values.cidr_block

        public_subnet_a_cidr  = [string]$PublicA.values.cidr_block
        public_subnet_b_cidr  = [string]$PublicB.values.cidr_block

        private_subnet_a_cidr = [string]$PrivateA.values.cidr_block
        private_subnet_b_cidr = [string]$PrivateB.values.cidr_block

        availability_zone_a = [string]$PublicA.values.availability_zone
        availability_zone_b = [string]$PublicB.values.availability_zone

        resource_name_prefix = $ResourceNamePrefix

        clinic_security_group_name =
            [string]$ClinicSg.values.name

        clinic_security_group_description =
            [string]$ClinicSg.values.description

        base_tags = $BaseTags
    }

    ExistingIds = [ordered]@{

        vpc_id = [string]$Vpc.values.id

        public_subnet_a_id =
            [string]$PublicA.values.id

        public_subnet_b_id =
            [string]$PublicB.values.id

        private_subnet_a_id =
            [string]$PrivateA.values.id

        private_subnet_b_id =
            [string]$PrivateB.values.id

        clinic_security_group_id =
            [string]$ClinicSg.values.id
    }

    Safety = [ordered]@{
        TerraformStateModified = $false
        AwsResourcesModified = $false
        TerraformSourceModified = $false
    }
}

Write-Host "Current exact module contract:"
Write-Host ""

$Contract |
    ConvertTo-Json -Depth 20