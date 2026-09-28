# ============================================================
# W2.6.4 — Interface Endpoint Readiness Discovery
# READ-ONLY
# Output:
#   w2.6.4-interface-endpoint-readiness.json
#   w2.6.4-interface-endpoint-readiness.sha256.txt
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [string]$Region = "ap-east-1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:AWS_PROFILE = $Profile

$OutputFile = "w2.6.4-interface-endpoint-readiness.json"
$HashFile   = "w2.6.4-interface-endpoint-readiness.sha256.txt"

$CollectorErrors = [System.Collections.Generic.List[object]]::new()

function Invoke-AwsJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CheckName,

        [Parameter(Mandatory = $true)]
        [string[]]$AwsArgs
    )

    $ErrFile = [System.IO.Path]::GetTempFileName()

    try {
        $Raw = & aws @AwsArgs 2>$ErrFile
        $ExitCode = $LASTEXITCODE

        $ErrText = ""
        if (Test-Path $ErrFile) {
            $ErrText = Get-Content $ErrFile -Raw -ErrorAction SilentlyContinue
        }

        if ($ExitCode -ne 0) {
            $CollectorErrors.Add(
                [pscustomobject]@{
                    Check    = $CheckName
                    ExitCode = $ExitCode
                    Error    = $ErrText.Trim()
                }
            )

            return $null
        }

        if ($null -eq $Raw) {
            return $null
        }

        $Text = ($Raw -join [Environment]::NewLine)

        if ([string]::IsNullOrWhiteSpace($Text)) {
            return $null
        }

        try {
            return ($Text | ConvertFrom-Json)
        }
        catch {
            $CollectorErrors.Add(
                [pscustomobject]@{
                    Check    = $CheckName
                    ExitCode = 0
                    Error    = "JSON parsing failed: $($_.Exception.Message)"
                }
            )

            return $null
        }
    }
    finally {
        Remove-Item $ErrFile -Force -ErrorAction SilentlyContinue
    }
}


Write-Host ""
Write-Host "[1/10] Reading Terraform outputs..." -ForegroundColor Cyan

$TfRaw = terraform output -json

if ($LASTEXITCODE -ne 0) {
    throw "terraform output -json failed."
}

$Tf = $TfRaw | ConvertFrom-Json

$VpcId = [string]$Tf.nonprod_vpc_id.value

$PrivateSubnetIds = @(
    [string]$Tf.nonprod_subnet_ids.value.private_a
    [string]$Tf.nonprod_subnet_ids.value.private_b
)

$ClinicSG = [string]$Tf.nonprod_security_group_ids.value.clinic_nonprod

if ([string]::IsNullOrWhiteSpace($VpcId)) {
    throw "Unable to resolve nonprod_vpc_id from Terraform."
}

if ($PrivateSubnetIds.Count -ne 2) {
    throw "Expected two private subnets from Terraform outputs."
}


Write-Host "[2/10] Collecting caller identity..." -ForegroundColor Cyan

$Caller = Invoke-AwsJson `
    -CheckName "CallerIdentity" `
    -AwsArgs @(
        "sts", "get-caller-identity",
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[3/10] Collecting VPC DNS attributes..." -ForegroundColor Cyan

$DnsSupport = Invoke-AwsJson `
    -CheckName "VpcDnsSupport" `
    -AwsArgs @(
        "ec2", "describe-vpc-attribute",
        "--vpc-id", $VpcId,
        "--attribute", "enableDnsSupport",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )

$DnsHostnames = Invoke-AwsJson `
    -CheckName "VpcDnsHostnames" `
    -AwsArgs @(
        "ec2", "describe-vpc-attribute",
        "--vpc-id", $VpcId,
        "--attribute", "enableDnsHostnames",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[4/10] Collecting private-subnet details..." -ForegroundColor Cyan

$SubnetFilter = $PrivateSubnetIds -join ","

$Subnets = Invoke-AwsJson `
    -CheckName "PrivateSubnets" `
    -AwsArgs @(
        "ec2", "describe-subnets",
        "--subnet-ids"
        $PrivateSubnetIds[0],
        $PrivateSubnetIds[1],
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[5/10] Collecting existing VPC endpoints..." -ForegroundColor Cyan

$VpcEndpoints = Invoke-AwsJson `
    -CheckName "ExistingVpcEndpoints" `
    -AwsArgs @(
        "ec2", "describe-vpc-endpoints",
        "--filters", "Name=vpc-id,Values=$VpcId",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[6/10] Collecting interface-endpoint service availability..." -ForegroundColor Cyan

$EndpointServices = Invoke-AwsJson `
    -CheckName "EndpointServices" `
    -AwsArgs @(
        "ec2", "describe-vpc-endpoint-services",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )

$CandidateServices = @(
    "ssm",
    "ssmmessages",
    "ec2messages",
    "logs",
    "kms",
    "sts",
    "secretsmanager"
)

$ServiceMatrix = foreach ($ShortName in $CandidateServices) {

    $FullName = "com.amazonaws.$Region.$ShortName"

    $Detail = $null

    if ($null -ne $EndpointServices) {
        $Detail = @(
            $EndpointServices.ServiceDetails |
            Where-Object { $_.ServiceName -eq $FullName }
        ) | Select-Object -First 1
    }

    $Types = @()

    if ($null -ne $Detail -and $null -ne $Detail.ServiceType) {
        $Types = @(
            $Detail.ServiceType |
            ForEach-Object { $_.ServiceType }
        )
    }

    [pscustomobject]@{
        ShortName   = $ShortName
        ServiceName = $FullName
        Available   = ($null -ne $Detail)
        Types       = $Types
    }
}


Write-Host "[7/10] Collecting private-subnet EC2 inventory..." -ForegroundColor Cyan

$Instances = Invoke-AwsJson `
    -CheckName "PrivateEc2Instances" `
    -AwsArgs @(
        "ec2", "describe-instances",
        "--filters", "Name=subnet-id,Values=$SubnetFilter",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[8/10] Collecting Systems Manager managed-node inventory..." -ForegroundColor Cyan

$SsmInventory = Invoke-AwsJson `
    -CheckName "SsmManagedNodes" `
    -AwsArgs @(
        "ssm", "describe-instance-information",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[9/10] Collecting private ENIs, route tables and SG rules..." -ForegroundColor Cyan

$PrivateEnis = Invoke-AwsJson `
    -CheckName "PrivateSubnetEnis" `
    -AwsArgs @(
        "ec2", "describe-network-interfaces",
        "--filters", "Name=subnet-id,Values=$SubnetFilter",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )

$PrivateRouteTables = @()

foreach ($SubnetId in $PrivateSubnetIds) {

    $Result = Invoke-AwsJson `
        -CheckName "RouteTable-$SubnetId" `
        -AwsArgs @(
            "ec2", "describe-route-tables",
            "--filters", "Name=association.subnet-id,Values=$SubnetId",
            "--region", $Region,
            "--output", "json",
            "--no-cli-pager"
        )

    if ($null -ne $Result) {
        $PrivateRouteTables += $Result.RouteTables
    }
}

$ClinicSgRules = Invoke-AwsJson `
    -CheckName "ClinicSecurityGroupRules" `
    -AwsArgs @(
        "ec2", "describe-security-group-rules",
        "--filters", "Name=group-id,Values=$ClinicSG",
        "--region", $Region,
        "--output", "json",
        "--no-cli-pager"
    )


Write-Host "[10/10] Building evidence JSON..." -ForegroundColor Cyan

$Ec2InstanceList = @()

if ($null -ne $Instances) {
    $Ec2InstanceList = @(
        $Instances.Reservations |
        ForEach-Object { $_.Instances }
    )
}

$SsmManagedList = @()

if ($null -ne $SsmInventory) {
    $SsmManagedList = @($SsmInventory.InstanceInformationList)
}

$ExistingEndpointList = @()

if ($null -ne $VpcEndpoints) {
    $ExistingEndpointList = @($VpcEndpoints.VpcEndpoints)
}

$Evidence = [ordered]@{

    EvidenceId = "W2.6.4"
    Purpose    = "Interface Endpoint Readiness and SSM Dependency Discovery"
    Timestamp  = (Get-Date).ToUniversalTime().ToString("o")
    Region     = $Region

    Terraform = [ordered]@{
        VpcId             = $VpcId
        PrivateSubnetIds  = $PrivateSubnetIds
        ClinicSecurityGroupId = $ClinicSG
    }

    CallerIdentity = $Caller

    VpcDns = [ordered]@{
        EnableDnsSupport   = if ($null -ne $DnsSupport) {
            $DnsSupport.EnableDnsSupport.Value
        } else {
            $null
        }

        EnableDnsHostnames = if ($null -ne $DnsHostnames) {
            $DnsHostnames.EnableDnsHostnames.Value
        } else {
            $null
        }
    }

    PrivateSubnets = if ($null -ne $Subnets) {
        $Subnets.Subnets
    } else {
        @()
    }

    ExistingVpcEndpoints = $ExistingEndpointList

    CandidateInterfaceEndpointServices = $ServiceMatrix

    PrivateEc2Instances = $Ec2InstanceList

    SsmManagedNodes = $SsmManagedList

    PrivateSubnetNetworkInterfaces = if ($null -ne $PrivateEnis) {
        $PrivateEnis.NetworkInterfaces
    } else {
        @()
    }

    PrivateRouteTables = $PrivateRouteTables

    ClinicSecurityGroupRules = if ($null -ne $ClinicSgRules) {
        $ClinicSgRules.SecurityGroupRules
    } else {
        @()
    }

    Summary = [ordered]@{
        DnsSupportEnabled = if ($null -ne $DnsSupport) {
            [bool]$DnsSupport.EnableDnsSupport.Value
        } else {
            $null
        }

        DnsHostnamesEnabled = if ($null -ne $DnsHostnames) {
            [bool]$DnsHostnames.EnableDnsHostnames.Value
        } else {
            $null
        }

        PrivateSubnetCount = $PrivateSubnetIds.Count

        ExistingVpcEndpointCount = $ExistingEndpointList.Count

        PrivateEc2InstanceCount = $Ec2InstanceList.Count

        SsmManagedNodeCount = $SsmManagedList.Count

        CollectorErrorCount = $CollectorErrors.Count
    }

    CollectorErrors = @($CollectorErrors)
}

$Evidence |
    ConvertTo-Json -Depth 20 |
    Set-Content -Encoding UTF8 $OutputFile

$Hash = Get-FileHash $OutputFile -Algorithm SHA256

"$($Hash.Hash)  $OutputFile" |
    Set-Content -Encoding ASCII $HashFile


Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "W2.6.4 discovery collection complete" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

Write-Host "Evidence file          : $OutputFile"
Write-Host "SHA-256 file           : $HashFile"
Write-Host "VPC                     : $VpcId"
Write-Host "Private subnet count    : $($PrivateSubnetIds.Count)"
Write-Host "Existing endpoints      : $($ExistingEndpointList.Count)"
Write-Host "Private EC2 instances   : $($Ec2InstanceList.Count)"
Write-Host "SSM managed nodes       : $($SsmManagedList.Count)"
Write-Host "Collector errors        : $($CollectorErrors.Count)"
Write-Host ""

$ServiceMatrix |
    Format-Table ShortName, Available, Types -AutoSize
