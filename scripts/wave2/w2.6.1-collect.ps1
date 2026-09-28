param(
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [string]$Region  = "ap-east-1",
    [string]$OutDir  = ".\evidence\W2.6.1"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$env:AWS_PROFILE = $Profile

Write-Host "========================================="
Write-Host " W2.6.1 Private Connectivity Discovery"
Write-Host "========================================="
Write-Host "Profile : $Profile"
Write-Host "Region  : $Region"
Write-Host ""

# ------------------------------------------------------------
# Helper: execute AWS CLI command and preserve failures
# ------------------------------------------------------------

function Invoke-AwsJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $errFile = Join-Path $env:TEMP (
        "w26-" + [guid]::NewGuid().ToString() + ".err"
    )

    try {

        # Execute AWS CLI.
        # Out-String guarantees stdout becomes a string.
        $stdout = (
            & aws @Arguments 2> $errFile |
            Out-String
        ).Trim()

        $exitCode = $LASTEXITCODE

        # Read stderr safely.
        # An empty stderr file can return $null,
        # therefore never call .Trim() directly on it.
        $stderrRaw = $null

        if (Test-Path $errFile) {
            $stderrRaw = Get-Content `
                $errFile `
                -Raw `
                -ErrorAction SilentlyContinue
        }

        if ($null -eq $stderrRaw) {
            $stderr = ""
        }
        else {
            $stderr = $stderrRaw.Trim()
        }

        # AWS CLI itself failed.
        if ($exitCode -ne 0) {

            return [pscustomobject]@{
                Success  = $false
                ExitCode = $exitCode
                Error    = $stderr
                Data     = $null
            }
        }

        # Successful command with legitimately empty output.
        if ([string]::IsNullOrWhiteSpace($stdout)) {

            return [pscustomobject]@{
                Success  = $true
                ExitCode = 0
                Error    = $null
                Data     = $null
            }
        }

        # Parse AWS JSON.
        try {

            $data = $stdout | ConvertFrom-Json

            return [pscustomobject]@{
                Success  = $true
                ExitCode = 0
                Error    = $null
                Data     = $data
            }
        }
        catch {

            return [pscustomobject]@{
                Success  = $false
                ExitCode = 0
                Error    = "JSON parsing failed: $($_.Exception.Message)"
                Data     = $stdout
            }
        }
    }
    finally {

        Remove-Item `
            $errFile `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------
# 1. Terraform identity / known architecture
# ------------------------------------------------------------

Write-Host "[1/9] Reading Terraform outputs..."

$VpcId = (terraform output -raw nonprod_vpc_id).Trim()

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read nonprod_vpc_id from Terraform."
}

$SubnetJson = terraform output -json nonprod_subnet_ids

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read nonprod_subnet_ids from Terraform."
}

$Subnets = $SubnetJson | ConvertFrom-Json

$PrivateSubnetIds = @(
    $Subnets.private_a
    $Subnets.private_b
)

# ------------------------------------------------------------
# 2. VPC endpoint inventory
# ------------------------------------------------------------

Write-Host "[2/9] Collecting VPC endpoints..."

$VpcEndpoints = Invoke-AwsJson @(
    "ec2", "describe-vpc-endpoints",
    "--region", $Region,
    "--filters", "Name=vpc-id,Values=$VpcId",
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 3. Route tables
# ------------------------------------------------------------

Write-Host "[3/9] Collecting route tables..."

$RouteTables = Invoke-AwsJson @(
    "ec2", "describe-route-tables",
    "--region", $Region,
    "--filters", "Name=vpc-id,Values=$VpcId",
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 4. NAT gateways
# ------------------------------------------------------------

Write-Host "[4/9] Collecting NAT gateways..."

$NatGateways = Invoke-AwsJson @(
    "ec2", "describe-nat-gateways",
    "--region", $Region,
    "--filter", "Name=vpc-id,Values=$VpcId",
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 5. Private-subnet network interfaces
# ------------------------------------------------------------

Write-Host "[5/9] Collecting private-subnet ENIs..."

$PrivateSubnetFilter = ($PrivateSubnetIds -join ",")

$NetworkInterfaces = Invoke-AwsJson @(
    "ec2", "describe-network-interfaces",
    "--region", $Region,
    "--filters", "Name=subnet-id,Values=$PrivateSubnetFilter",
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 6. EC2 workload inventory
# ------------------------------------------------------------

Write-Host "[6/9] Collecting EC2 workload inventory..."

$Ec2Instances = Invoke-AwsJson @(
    "ec2", "describe-instances",
    "--region", $Region,
    "--filters", "Name=vpc-id,Values=$VpcId",
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 7. Directory Service inventory
# ------------------------------------------------------------

Write-Host "[7/9] Collecting Directory Service inventory..."

$Directories = Invoke-AwsJson @(
    "ds", "describe-directories",
    "--region", $Region,
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 8. FSx inventory
# ------------------------------------------------------------

Write-Host "[8/9] Collecting FSx inventory..."

$Fsx = Invoke-AwsJson @(
    "fsx", "describe-file-systems",
    "--region", $Region,
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# 9. Endpoint services available in ap-east-1
# ------------------------------------------------------------

Write-Host "[9/9] Collecting available endpoint services..."

$EndpointServices = Invoke-AwsJson @(
    "ec2", "describe-vpc-endpoint-services",
    "--region", $Region,
    "--output", "json",
    "--no-cli-pager"
)

# ------------------------------------------------------------
# Derive useful evidence
# ------------------------------------------------------------

$PrivateRouteTables = @()

if ($RouteTables.Success) {

    foreach ($rt in @($RouteTables.Data.RouteTables)) {

        $matchingAssociations = @(
            $rt.Associations |
            Where-Object {
                $_.SubnetId -and
                $PrivateSubnetIds -contains $_.SubnetId
            }
        )

        if ($matchingAssociations.Count -gt 0) {

            $PrivateRouteTables += [pscustomobject]@{
                RouteTableId = $rt.RouteTableId

                Subnets = @(
                    $matchingAssociations |
                    ForEach-Object {
                        $_.SubnetId
                    }
                )

                Routes = @(
                    $rt.Routes |
                    ForEach-Object {
                        [pscustomobject]@{
                            DestinationCidrBlock     = $_.DestinationCidrBlock
                            DestinationPrefixListId = $_.DestinationPrefixListId
                            GatewayId                = $_.GatewayId
                            NatGatewayId             = $_.NatGatewayId
                            VpcEndpointId            = $_.VpcEndpointId
                            State                    = $_.State
                        }
                    }
                )
            }
        }
    }
}

# ------------------------------------------------------------
# Relevant endpoint candidates
# ------------------------------------------------------------

$CandidateEndpointServices = @()

if ($EndpointServices.Success) {

    $Candidates = @(
        ".s3",
        ".dynamodb",
        ".ssm",
        ".ssmmessages",
        ".ec2messages",
        ".kms",
        ".logs",
        ".secretsmanager",
        ".sts",
        ".ecr.api",
        ".ecr.dkr"
    )

    foreach ($service in @($EndpointServices.Data.ServiceNames)) {

        foreach ($candidate in $Candidates) {

            if ($service.EndsWith($candidate)) {
                $CandidateEndpointServices += $service
                break
            }
        }
    }

    $CandidateEndpointServices =
        $CandidateEndpointServices |
        Sort-Object -Unique
}

# ------------------------------------------------------------
# Compact workload view
# ------------------------------------------------------------

$EniSummary = @()

if ($NetworkInterfaces.Success) {

    $EniSummary = @(
        $NetworkInterfaces.Data.NetworkInterfaces |
        ForEach-Object {

            [pscustomobject]@{
                NetworkInterfaceId = $_.NetworkInterfaceId
                Description        = $_.Description
                InterfaceType      = $_.InterfaceType
                RequesterManaged   = $_.RequesterManaged
                Status             = $_.Status
                SubnetId           = $_.SubnetId
                PrivateIpAddress   = $_.PrivateIpAddress

                SecurityGroups = @(
                    $_.Groups |
                    ForEach-Object {
                        [pscustomobject]@{
                            GroupId   = $_.GroupId
                            GroupName = $_.GroupName
                        }
                    }
                )
            }
        }
    )
}

# ------------------------------------------------------------
# Preserve collector errors
# ------------------------------------------------------------

$CollectorErrors = @()

$Checks = [ordered]@{
    VpcEndpoints      = $VpcEndpoints
    RouteTables       = $RouteTables
    NatGateways       = $NatGateways
    NetworkInterfaces = $NetworkInterfaces
    Ec2Instances      = $Ec2Instances
    Directories       = $Directories
    Fsx               = $Fsx
    EndpointServices  = $EndpointServices
}

foreach ($entry in $Checks.GetEnumerator()) {

    if (-not $entry.Value.Success) {

        $CollectorErrors += [pscustomobject]@{
            Check    = $entry.Key
            ExitCode = $entry.Value.ExitCode
            Error    = $entry.Value.Error
        }
    }
}

# ------------------------------------------------------------
# Final evidence object
# ------------------------------------------------------------

$Evidence = [ordered]@{

    Evidence = [ordered]@{
        Stage          = "W2.6.1"
        Purpose        = "Private connectivity and VPC endpoint resource discovery"
        GeneratedUtc   = (Get-Date).ToUniversalTime().ToString("o")
        ReadOnly       = $true
        AwsProfile     = $Profile
        Region         = $Region
    }

    Terraform = [ordered]@{
        VpcId = $VpcId

        Subnets = [ordered]@{
            PrivateA = $Subnets.private_a
            PrivateB = $Subnets.private_b
            PublicA  = $Subnets.public_a
            PublicB  = $Subnets.public_b
        }
    }

    Summary = [ordered]@{

        ExistingVpcEndpointCount =
            if ($VpcEndpoints.Success) {
                @($VpcEndpoints.Data.VpcEndpoints).Count
            }
            else {
                $null
            }

        NatGatewayCount =
            if ($NatGateways.Success) {
                @($NatGateways.Data.NatGateways).Count
            }
            else {
                $null
            }

        PrivateSubnetEniCount =
            if ($NetworkInterfaces.Success) {
                @($NetworkInterfaces.Data.NetworkInterfaces).Count
            }
            else {
                $null
            }

        PrivateRouteTableCount =
            @($PrivateRouteTables).Count

        CandidateEndpointServices =
            $CandidateEndpointServices
    }

    PrivateRouteTables =
        $PrivateRouteTables

    PrivateSubnetNetworkInterfaces =
        $EniSummary

    VpcEndpoints =
        if ($VpcEndpoints.Success) {
            $VpcEndpoints.Data.VpcEndpoints
        }
        else {
            $null
        }

    NatGateways =
        if ($NatGateways.Success) {
            $NatGateways.Data.NatGateways
        }
        else {
            $null
        }

    DirectoryService =
        if ($Directories.Success) {
            $Directories.Data.DirectoryDescriptions
        }
        else {
            $null
        }

    FileSystems =
        if ($Fsx.Success) {
            $Fsx.Data.FileSystems
        }
        else {
            $null
        }

    Ec2Reservations =
        if ($Ec2Instances.Success) {
            $Ec2Instances.Data.Reservations
        }
        else {
            $null
        }

    CollectorErrors =
        $CollectorErrors
}

# ------------------------------------------------------------
# Write JSON evidence
# ------------------------------------------------------------

$JsonPath = Join-Path $OutDir "w2.6.1-resource-baseline.json"

$Evidence |
    ConvertTo-Json -Depth 30 |
    Set-Content -Path $JsonPath -Encoding UTF8

# ------------------------------------------------------------
# SHA-256 evidence
# ------------------------------------------------------------

$Hash = Get-FileHash $JsonPath -Algorithm SHA256

$HashPath = Join-Path $OutDir "w2.6.1-resource-baseline.sha256.txt"

"$($Hash.Hash)  $($Hash.Path | Split-Path -Leaf)" |
    Set-Content $HashPath

Write-Host ""
Write-Host "========================================="
Write-Host " Collection complete"
Write-Host "========================================="
Write-Host "JSON   : $JsonPath"
Write-Host "SHA256 : $HashPath"
Write-Host ""

Write-Host "Existing VPC endpoints : $($Evidence.Summary.ExistingVpcEndpointCount)"
Write-Host "NAT gateways           : $($Evidence.Summary.NatGatewayCount)"
Write-Host "Private ENIs           : $($Evidence.Summary.PrivateSubnetEniCount)"
Write-Host "Private route tables   : $($Evidence.Summary.PrivateRouteTableCount)"
Write-Host "Collector errors       : $($CollectorErrors.Count)"
