param(
    [switch]$ApplyCleanup
)

$ErrorActionPreference = "Stop"

$NonProdRoot = $PSScriptRoot
$ProjectRoot = (Resolve-Path (Join-Path $NonProdRoot "..\..")).Path
$ModuleRoot  = Join-Path $ProjectRoot "modules\network"

$EvidenceRoot = Join-Path $NonProdRoot "evidence\W2.8"
$ScriptArchive = Join-Path $ProjectRoot "scripts\wave2"

$ProjectParent = Split-Path $ProjectRoot -Parent
$PrivateArchiveRoot = Join-Path `
    $ProjectParent `
    "clinic-cloud-iac-private-archive\Wave2"

New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null

$CleanupActions = @()
$Findings       = @()
$Checks         = [ordered]@{}

Set-Location $NonProdRoot


# ===================================================================
# Helper functions
# ===================================================================

function Add-Finding {
    param(
        [string]$Id,
        [string]$Classification,
        [string]$Description
    )

    $script:Findings += [ordered]@{
        Id             = $Id
        Classification = $Classification
        Description    = $Description
    }
}


function Get-TagValue {
    param(
        $Tags,
        [string]$Key
    )

    if ($null -eq $Tags) {
        return $null
    }

    $Match = @(
        $Tags |
        Where-Object { $_.Key -eq $Key }
    )

    if ($Match.Count -eq 0) {
        return $null
    }

    return $Match[0].Value
}


function Test-SetEqual {
    param(
        [object[]]$A,
        [object[]]$B
    )

    $A1 = @($A | Sort-Object -Unique)
    $B1 = @($B | Sort-Object -Unique)

    if ($A1.Count -ne $B1.Count) {
        return $false
    }

    foreach ($Item in $A1) {
        if ($Item -notin $B1) {
            return $false
        }
    }

    return $true
}


function Move-ToPrivateArchive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Category
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }

    $DestinationDirectory = Join-Path $PrivateArchiveRoot $Category

    New-Item `
        -ItemType Directory `
        -Path $DestinationDirectory `
        -Force |
        Out-Null

    $Name = Split-Path $Source -Leaf
    $Destination = Join-Path $DestinationDirectory $Name

    if (Test-Path -LiteralPath $Destination) {

        $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

        $Destination = Join-Path `
            $DestinationDirectory `
            "$Stamp-$Name"
    }

    Move-Item `
        -LiteralPath $Source `
        -Destination $Destination

    $script:CleanupActions += [ordered]@{
        Action      = "ARCHIVE"
        Source      = $Source
        Destination = $Destination
    }
}


function Invoke-CleanTerraformPlan {

    Set-Location $NonProdRoot

    $ValidateOutput = @(
        terraform validate 2>&1
    )

    $ValidateCode = $LASTEXITCODE

    if ($ValidateCode -ne 0) {

        return [ordered]@{
            Valid      = $false
            PlanClean  = $false
            PlanExit   = $null
            Validation = @($ValidateOutput | ForEach-Object { $_.ToString() })
            Plan       = @()
        }
    }

    $PlanOutput = @(
        terraform plan -detailed-exitcode -no-color 2>&1
    )

    $PlanCode = $LASTEXITCODE

    return [ordered]@{
        Valid      = $true
        PlanClean  = ($PlanCode -eq 0)
        PlanExit   = $PlanCode
        Validation = @($ValidateOutput | ForEach-Object { $_.ToString() })
        Plan       = @($PlanOutput | ForEach-Object { $_.ToString() })
    }
}


# ===================================================================
# W2.8.2 — Repository / Terraform classification
# ===================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8.2 - REPOSITORY AND TERRAFORM CLASSIFICATION"
Write-Host "============================================================"
Write-Host ""


# -------------------------------------------------------------------
# Git repository verification
# -------------------------------------------------------------------

Set-Location $ProjectRoot

$GitTop = git rev-parse --show-toplevel 2>$null

if ($LASTEXITCODE -ne 0) {
    throw "Project root is not a Git repository."
}

$Tracked = @(
    git ls-files
)

$Untracked = @(
    git ls-files --others --exclude-standard
)

$Ignored = @(
    git ls-files --others --ignored --exclude-standard
)

$RiskPattern = `
    '(^|/)\.terraform(/|$)|' +
    '\.tfstate($|\.)|' +
    '\.tfplan$|' +
    '\.tfvars$|' +
    '\.tfvars\.json$|' +
    '\.pre-w2\.7\.5\.3$'

$TrackedRisk = @(
    $Tracked |
    Where-Object { $_ -match $RiskPattern }
)

$UntrackedRisk = @(
    $Untracked |
    Where-Object { $_ -match $RiskPattern }
)

$IgnoredRisk = @(
    $Ignored |
    Where-Object { $_ -match $RiskPattern }
)

# -------------------------------------------------------------------
# Explicitly allow tracked terraform.tfvars.example templates
# -------------------------------------------------------------------

$TrackedTfvarsExamples = @(
    $Tracked |
    Where-Object {
        $_ -match '\.tfvars\.example$'
    }
)

$Checks["TrackedTfvarsExampleCount"] = $TrackedTfvarsExamples.Count

if ($TrackedTfvarsExamples.Count -gt 0) {
    Add-Finding `
        "GIT-TFVARS-EXAMPLE" `
        "PASS" `
        "$($TrackedTfvarsExamples.Count) tracked terraform.tfvars.example templates are intentionally retained."
}

$Checks["GitTrackedRiskCount"]   = $TrackedRisk.Count
$Checks["GitUntrackedRiskCount"] = $UntrackedRisk.Count
$Checks["GitIgnoredRiskCount"]   = $IgnoredRisk.Count

if ($TrackedRisk.Count -gt 0) {

    Add-Finding `
        "GIT-001" `
        "BLOCKER" `
        "$($TrackedRisk.Count) risky Terraform artifacts are tracked by Git."
}
else {

    Add-Finding `
        "GIT-001" `
        "PASS" `
        "No Terraform state, plans, tfvars, cache contents, or rollback artifacts are tracked by Git."
}


# -------------------------------------------------------------------
# Backend determination
# -------------------------------------------------------------------

$BackendFile = Join-Path $NonProdRoot "backend.tf"

$BackendType = "implicit-local"

if (Test-Path $BackendFile) {

    $BackendText = Get-Content $BackendFile -Raw

    if ($BackendText -match 'backend\s+"([^"]+)"') {
        $BackendType = $Matches[1]
    }
}

$RemoteBackend = (
    $BackendType -ne "local" -and
    $BackendType -ne "implicit-local"
)

$Checks["BackendType"]   = $BackendType
$Checks["RemoteBackend"] = $RemoteBackend

$RemoteStateReadable = $false

if ($RemoteBackend) {

    Set-Location $NonProdRoot

    $StatePull = terraform state pull 2>$null | Out-String

    if (
        $LASTEXITCODE -eq 0 -and
        $StatePull.Trim().StartsWith("{")
    ) {
        $RemoteStateReadable = $true
    }
}

$Checks["RemoteStateReadable"] = $RemoteStateReadable


# -------------------------------------------------------------------
# Terraform state structure
# -------------------------------------------------------------------

Set-Location $NonProdRoot

$StateResources = @(
    terraform state list
)

if ($LASTEXITCODE -ne 0) {
    throw "terraform state list failed."
}

$ModuleResources = @(
    $StateResources |
    Where-Object { $_ -like "module.network.*" }
)

$OldRootResources = @(
    $StateResources |
    Where-Object {
        $_ -match '^aws_vpc\.clinic_nonprod$' -or
        $_ -match '^aws_subnet\.(public_a|public_b|private_a|private_b)$' -or
        $_ -match '^aws_internet_gateway\.clinic_nonprod$' -or
        $_ -match '^aws_route_table\.(public|private_a|private_b)$' -or
        $_ -match '^aws_route\.public_internet$' -or
        $_ -match '^aws_route_table_association\.(public_a|public_b|private_a|private_b)$' -or
        $_ -match '^aws_security_group\.clinic_nonprod$' -or
        $_ -match '^aws_default_security_group\.clinic_nonprod$' -or
        $_ -match '^aws_vpc_security_group_egress_rule\.clinic_to_directory$' -or
        $_ -match '^aws_vpc_endpoint\.s3_gateway$'
    }
)

$Checks["ModuleNetworkResources"] = $ModuleResources.Count
$Checks["OldRootResources"]      = $OldRootResources.Count

if (
    $ModuleResources.Count -eq 18 -and
    $OldRootResources.Count -eq 0
) {

    Add-Finding `
        "TFSTATE-001" `
        "PASS" `
        "All 18 network resources are inside module.network and no old root addresses remain."
}
else {

    Add-Finding `
        "TFSTATE-001" `
        "BLOCKER" `
        "Unexpected Terraform network state structure."
}


# -------------------------------------------------------------------
# Current clean plan
# -------------------------------------------------------------------

$PreCleanupTerraform = Invoke-CleanTerraformPlan

$Checks["PreCleanupValidate"] = $PreCleanupTerraform.Valid
$Checks["PreCleanupPlanExit"] = $PreCleanupTerraform.PlanExit
$Checks["PreCleanupPlanClean"] = $PreCleanupTerraform.PlanClean

if ($PreCleanupTerraform.PlanClean) {

    Add-Finding `
        "TFPLAN-001" `
        "PASS" `
        "Terraform currently reports no infrastructure changes."
}
else {

    Add-Finding `
        "TFPLAN-001" `
        "BLOCKER" `
        "Terraform configuration is not currently reconciled."
}


# -------------------------------------------------------------------
# Artifact discovery
# -------------------------------------------------------------------

$RollbackFiles = @(
    Get-ChildItem $NonProdRoot -File |
    Where-Object {
        $_.Name -like "*.pre-w2.7.5.3"
    }
)

$PlanFiles = @(
    Get-ChildItem $NonProdRoot -File |
    Where-Object {
        $_.Extension -eq ".tfplan"
    }
)

$LocalStateFiles = @(
    Get-ChildItem $NonProdRoot -File |
    Where-Object {
        $_.Name -like "terraform.tfstate*"
    }
)

$FinalPlanPath = Join-Path $NonProdRoot '$FinalPlan'
$FinalPlanPresent = Test-Path -LiteralPath $FinalPlanPath

$EndpointPath = Join-Path $NonProdRoot "endpoint.tf"
$EndpointStale = $false

if (Test-Path $EndpointPath) {

    $EndpointText = Get-Content $EndpointPath -Raw

    if (
        $EndpointText -match 'No VPC endpoints are created' -or
        (
            $EndpointText -match '(?i)s3' -and
            $EndpointText -match 'enabled\s*=\s*false'
        )
    ) {
        $EndpointStale = $true
    }
}

$Checks["RollbackFiles"]       = $RollbackFiles.Count
$Checks["PlanFiles"]           = $PlanFiles.Count
$Checks["LocalStateFiles"]     = $LocalStateFiles.Count
$Checks["FinalPlanPresent"]    = $FinalPlanPresent
$Checks["EndpointCatalogStale"] = $EndpointStale

if ($RollbackFiles.Count -gt 0) {
    Add-Finding `
        "REPO-ROLLBACK" `
        "CLEANUP" `
        "$($RollbackFiles.Count) W2.7 rollback files remain."
}

if ($PlanFiles.Count -gt 0) {
    Add-Finding `
        "REPO-PLAN" `
        "CLEANUP" `
        "$($PlanFiles.Count) historical binary Terraform plans remain locally."
}

if ($LocalStateFiles.Count -gt 0) {

    if ($RemoteBackend -and $RemoteStateReadable) {

        Add-Finding `
            "REPO-STATE" `
            "CLEANUP" `
            "$($LocalStateFiles.Count) local state/backups remain even though the configured remote backend is readable."
    }
    else {

        Add-Finding `
            "REPO-STATE" `
            "HOLD" `
            "Local state files exist, but remote backend safety has not been proven."
    }
}

if ($FinalPlanPresent) {
    Add-Finding `
        "REPO-FINALPLAN" `
        "CLEANUP" `
        "Literal `$FinalPlan temporary artifact exists."
}

if ($EndpointStale) {
    Add-Finding `
        "REPO-ENDPOINT" `
        "CLEANUP-CANDIDATE" `
        "endpoint.tf appears inconsistent with the live S3 Gateway Endpoint architecture."
}


# ===================================================================
# W2.8.3 — Live network/security verification
# ===================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8.3 - LIVE NETWORK / SECURITY VERIFICATION"
Write-Host "============================================================"
Write-Host ""

Set-Location $NonProdRoot


# -------------------------------------------------------------------
# Terraform outputs
# -------------------------------------------------------------------

$VpcId = (terraform output -raw nonprod_vpc_id).Trim()
$Region = (terraform output -raw aws_region).Trim()
$AccountId = (terraform output -raw aws_account_id).Trim()
$EndpointId = (terraform output -raw nonprod_s3_gateway_endpoint_id).Trim()

$SubnetIdsRaw = terraform output -json nonprod_subnet_ids | Out-String
$SubnetIds = $SubnetIdsRaw | ConvertFrom-Json

$SecurityGroupIdsRaw = terraform output -json nonprod_security_group_ids | Out-String
$SecurityGroupIds = $SecurityGroupIdsRaw | ConvertFrom-Json


# -------------------------------------------------------------------
# VPC DNS
# -------------------------------------------------------------------

$DnsSupportRaw = aws ec2 describe-vpc-attribute `
    --vpc-id $VpcId `
    --attribute enableDnsSupport `
    --region $Region `
    --output json |
    Out-String

$DnsHostnamesRaw = aws ec2 describe-vpc-attribute `
    --vpc-id $VpcId `
    --attribute enableDnsHostnames `
    --region $Region `
    --output json |
    Out-String

$DnsSupport = $DnsSupportRaw | ConvertFrom-Json
$DnsHostnames = $DnsHostnamesRaw | ConvertFrom-Json

$Checks["DnsSupport"]   = [bool]$DnsSupport.EnableDnsSupport.Value
$Checks["DnsHostnames"] = [bool]$DnsHostnames.EnableDnsHostnames.Value

if (
    $Checks["DnsSupport"] -and
    $Checks["DnsHostnames"]
) {
    Add-Finding `
        "NET-DNS" `
        "PASS" `
        "VPC DNS support and DNS hostnames are enabled."
}
else {
    Add-Finding `
        "NET-DNS" `
        "BLOCKER" `
        "Required VPC DNS capability is disabled."
}


# -------------------------------------------------------------------
# Subnet security
# -------------------------------------------------------------------

$SubnetRaw = aws ec2 describe-subnets `
    --subnet-ids `
        $SubnetIds.public_a `
        $SubnetIds.public_b `
        $SubnetIds.private_a `
        $SubnetIds.private_b `
    --region $Region `
    --output json |
    Out-String

$SubnetData = $SubnetRaw | ConvertFrom-Json

$PublicIpEnabled = @(
    $SubnetData.Subnets |
    Where-Object { $_.MapPublicIpOnLaunch -eq $true }
)

$Checks["SubnetsWithAutomaticPublicIp"] = $PublicIpEnabled.Count

if ($PublicIpEnabled.Count -eq 0) {

    Add-Finding `
        "NET-SUBNET" `
        "PASS" `
        "None of the four subnets automatically assign public IPv4 addresses."
}
else {

    Add-Finding `
        "NET-SUBNET" `
        "BLOCKER" `
        "$($PublicIpEnabled.Count) subnets automatically assign public IPv4 addresses."
}


# -------------------------------------------------------------------
# Route table verification
# -------------------------------------------------------------------

$RouteRaw = aws ec2 describe-route-tables `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region $Region `
    --output json |
    Out-String

$RouteData = $RouteRaw | ConvertFrom-Json


function Get-RouteTableForSubnet {
    param([string]$SubnetId)

    return @(
        $RouteData.RouteTables |
        Where-Object {
            @(
                $_.Associations |
                Where-Object {
                    $_.SubnetId -eq $SubnetId
                }
            ).Count -gt 0
        }
    )[0]
}


$PublicRouteA = Get-RouteTableForSubnet $SubnetIds.public_a
$PublicRouteB = Get-RouteTableForSubnet $SubnetIds.public_b

$PrivateRouteA = Get-RouteTableForSubnet $SubnetIds.private_a
$PrivateRouteB = Get-RouteTableForSubnet $SubnetIds.private_b

$PublicRouteShared = (
    $PublicRouteA.RouteTableId -eq
    $PublicRouteB.RouteTableId
)

$PublicDefaultRoute = @(
    $PublicRouteA.Routes |
    Where-Object {
        $_.DestinationCidrBlock -eq "0.0.0.0/0" -and
        $_.GatewayId -like "igw-*"
    }
)

$PrivateADefault = @(
    $PrivateRouteA.Routes |
    Where-Object {
        $_.DestinationCidrBlock -eq "0.0.0.0/0"
    }
)

$PrivateBDefault = @(
    $PrivateRouteB.Routes |
    Where-Object {
        $_.DestinationCidrBlock -eq "0.0.0.0/0"
    }
)

$PrivateAS3 = @(
    $PrivateRouteA.Routes |
    Where-Object {
        $_.GatewayId -eq $EndpointId
    }
)

$PrivateBS3 = @(
    $PrivateRouteB.Routes |
    Where-Object {
        $_.GatewayId -eq $EndpointId
    }
)

$Checks["PublicSubnetsShareRouteTable"] = $PublicRouteShared
$Checks["PublicInternetRouteCount"] = $PublicDefaultRoute.Count
$Checks["PrivateADefaultRoutes"] = $PrivateADefault.Count
$Checks["PrivateBDefaultRoutes"] = $PrivateBDefault.Count
$Checks["PrivateAS3Routes"] = $PrivateAS3.Count
$Checks["PrivateBS3Routes"] = $PrivateBS3.Count

if (
    $PublicRouteShared -and
    $PublicDefaultRoute.Count -eq 1 -and
    $PrivateADefault.Count -eq 0 -and
    $PrivateBDefault.Count -eq 0 -and
    $PrivateAS3.Count -eq 1 -and
    $PrivateBS3.Count -eq 1
) {

    Add-Finding `
        "NET-ROUTES" `
        "PASS" `
        "Public/private routing boundaries and private S3 endpoint routes are correct."
}
else {

    Add-Finding `
        "NET-ROUTES" `
        "BLOCKER" `
        "Unexpected public/private routing condition detected."
}


# -------------------------------------------------------------------
# Security groups
# -------------------------------------------------------------------

$SgRaw = aws ec2 describe-security-groups `
    --group-ids `
        $SecurityGroupIds.clinic_nonprod `
        $SecurityGroupIds.default `
        $SecurityGroupIds.directory_controllers `
    --region $Region `
    --output json |
    Out-String

$SgData = $SgRaw | ConvertFrom-Json

$ClinicSg = @(
    $SgData.SecurityGroups |
    Where-Object {
        $_.GroupId -eq $SecurityGroupIds.clinic_nonprod
    }
)[0]

$DefaultSg = @(
    $SgData.SecurityGroups |
    Where-Object {
        $_.GroupId -eq $SecurityGroupIds.default
    }
)[0]

$DirectorySg = @(
    $SgData.SecurityGroups |
    Where-Object {
        $_.GroupId -eq $SecurityGroupIds.directory_controllers
    }
)[0]

$ClinicIngressCount = @($ClinicSg.IpPermissions).Count
$ClinicEgressCount  = @($ClinicSg.IpPermissionsEgress).Count

$ClinicDirectoryReferences = @()

foreach ($Rule in @($ClinicSg.IpPermissionsEgress)) {

    foreach ($Pair in @($Rule.UserIdGroupPairs)) {

        if (
            $Pair.GroupId -eq
            $SecurityGroupIds.directory_controllers
        ) {
            $ClinicDirectoryReferences += $Pair.GroupId
        }
    }
}

$DefaultIngressCount = @($DefaultSg.IpPermissions).Count
$DefaultEgressCount  = @($DefaultSg.IpPermissionsEgress).Count

$Checks["ClinicIngressRules"] = $ClinicIngressCount
$Checks["ClinicEgressRules"] = $ClinicEgressCount
$Checks["ClinicDirectoryReferences"] = $ClinicDirectoryReferences.Count

$Checks["DefaultSgIngressRules"] = $DefaultIngressCount
$Checks["DefaultSgEgressRules"] = $DefaultEgressCount

if (
    $ClinicIngressCount -eq 0 -and
    $ClinicEgressCount -eq 1 -and
    $ClinicDirectoryReferences.Count -eq 1
) {

    Add-Finding `
        "SG-CLINIC" `
        "PASS" `
        "Clinic SG has no ingress and its single egress boundary targets the Directory Service SG."
}
else {

    Add-Finding `
        "SG-CLINIC" `
        "BLOCKER" `
        "Clinic SG differs from the approved security boundary."
}

if (
    $DefaultIngressCount -eq 0 -and
    $DefaultEgressCount -eq 0
) {

    Add-Finding `
        "SG-DEFAULT" `
        "PASS" `
        "Default VPC security group has no ingress or egress rules."
}
else {

    Add-Finding `
        "SG-DEFAULT" `
        "BLOCKER" `
        "Default VPC security group is not empty."
}

Add-Finding `
    "SG-DIRECTORY" `
    "ACCEPTED-EXTERNAL" `
    "Directory controller SG is an external AWS Directory Service dependency and is not modified by module.network."


# -------------------------------------------------------------------
# S3 endpoint
# -------------------------------------------------------------------

$EndpointRaw = aws ec2 describe-vpc-endpoints `
    --vpc-endpoint-ids $EndpointId `
    --region $Region `
    --output json |
    Out-String

$EndpointData = $EndpointRaw | ConvertFrom-Json

$S3Endpoint = $EndpointData.VpcEndpoints[0]

$ExpectedEndpointRouteTables = @(
    $PrivateRouteA.RouteTableId,
    $PrivateRouteB.RouteTableId
)

$EndpointRouteTablesCorrect = Test-SetEqual `
    @($S3Endpoint.RouteTableIds) `
    $ExpectedEndpointRouteTables

$EndpointPolicy = $S3Endpoint.PolicyDocument |
    ConvertFrom-Json

$Statement = $EndpointPolicy.Statement[0]

$PrincipalAccount = $null
$ResourceAccount = $null

if ($null -ne $Statement.Condition.StringEquals) {

    $PrincipalProperty =
        $Statement.Condition.StringEquals.PSObject.Properties[
            "aws:PrincipalAccount"
        ]

    $ResourceProperty =
        $Statement.Condition.StringEquals.PSObject.Properties[
            "s3:ResourceAccount"
        ]

    if ($null -ne $PrincipalProperty) {
        $PrincipalAccount = $PrincipalProperty.Value
    }

    if ($null -ne $ResourceProperty) {
        $ResourceAccount = $ResourceProperty.Value
    }
}

$EndpointPolicyAccountBound = (
    $PrincipalAccount -eq $AccountId -and
    $ResourceAccount -eq $AccountId
)

$Checks["S3EndpointState"] = $S3Endpoint.State
$Checks["S3EndpointType"] = $S3Endpoint.VpcEndpointType
$Checks["S3EndpointRouteTablesCorrect"] = $EndpointRouteTablesCorrect
$Checks["S3EndpointPolicyAccountBound"] = $EndpointPolicyAccountBound

if (
    $S3Endpoint.State -eq "available" -and
    $S3Endpoint.VpcEndpointType -eq "Gateway" -and
    $EndpointRouteTablesCorrect -and
    $EndpointPolicyAccountBound
) {

    Add-Finding `
        "VPCE-S3" `
        "PASS" `
        "S3 Gateway Endpoint is available, private-route scoped, and account constrained."
}
else {

    Add-Finding `
        "VPCE-S3" `
        "BLOCKER" `
        "S3 Gateway Endpoint does not match the approved Wave 2 boundary."
}

Add-Finding `
    "VPCE-S3-LP" `
    "FUTURE-HARDENING" `
    "Endpoint policy remains account-scoped with s3:* and Resource=*; narrow later when actual workload buckets/actions are known."


# ===================================================================
# W2.8.4 — Findings classification
# ===================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8.4 - FINDINGS CLASSIFICATION"
Write-Host "============================================================"
Write-Host ""

$Blockers = @(
    $Findings |
    Where-Object {
        $_.Classification -eq "BLOCKER"
    }
)

$CleanupFindings = @(
    $Findings |
    Where-Object {
        $_.Classification -like "CLEANUP*"
    }
)

$PassFindings = @(
    $Findings |
    Where-Object {
        $_.Classification -eq "PASS"
    }
)

Write-Host "PASS findings:       $($PassFindings.Count)"
Write-Host "Cleanup findings:    $($CleanupFindings.Count)"
Write-Host "Blocking findings:   $($Blockers.Count)"
Write-Host ""

foreach ($Finding in $Findings) {

    Write-Host (
        "[{0}] {1} - {2}" -f `
        $Finding.Classification,
        $Finding.Id,
        $Finding.Description
    )
}


# ===================================================================
# Save audit evidence
# ===================================================================

$AuditEvidence = [ordered]@{
    EvidenceId = "W2.8.4"
    Purpose = "Wave 2 Closeout Classification"
    Timestamp = (Get-Date).ToUniversalTime().ToString("o")
    Checks = $Checks
    Findings = @($Findings)

    Summary = [ordered]@{
        PassFindings = $PassFindings.Count
        CleanupFindings = $CleanupFindings.Count
        Blockers = $Blockers.Count
        CleanupRequested = [bool]$ApplyCleanup
    }
}

$AuditFile = Join-Path `
    $EvidenceRoot `
    "w2.8.4-classification.json"

$AuditEvidence |
    ConvertTo-Json -Depth 30 |
    Set-Content $AuditFile -Encoding UTF8


# ===================================================================
# Stop here during audit-only mode
# ===================================================================

if (-not $ApplyCleanup) {

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " W2.8 AUDIT COMPLETE"
    Write-Host "============================================================"

    Write-Host ""
    Write-Host "No files, Terraform state, or AWS resources were modified."
    Write-Host ""
    Write-Host "Classification evidence:"
    Write-Host " $AuditFile"

    if ($Blockers.Count -gt 0) {

        Write-Host ""
        Write-Host "BLOCKERS EXIST."
        Write-Host "Do NOT run -ApplyCleanup until they are reviewed."
        exit 2
    }

    Write-Host ""
    Write-Host "No infrastructure blockers detected."
    Write-Host ""
    Write-Host "Next command:"
    Write-Host ""
    Write-Host "powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -ApplyCleanup"

    exit 0
}


# ===================================================================
# W2.8.5 — Safe remediation / cleanup
# ===================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8.5 - SAFE CLEANUP"
Write-Host "============================================================"
Write-Host ""

if ($Blockers.Count -gt 0) {
    throw "W2.8.5 aborted because blocking security/infrastructure findings exist."
}


# -------------------------------------------------------------------
# Archive W2.7 rollback files
# -------------------------------------------------------------------

foreach ($File in $RollbackFiles) {

    Move-ToPrivateArchive `
        $File.FullName `
        "rollback"
}


# -------------------------------------------------------------------
# Archive historical Terraform binary plans
# -------------------------------------------------------------------

foreach ($File in $PlanFiles) {

    Move-ToPrivateArchive `
        $File.FullName `
        "terraform-plans"
}


# -------------------------------------------------------------------
# Archive local NonProd state/backups only if the remote backend
# is positively identified and readable.
#
# Bootstrap stack state is intentionally NOT touched.
# -------------------------------------------------------------------

if (
    $RemoteBackend -and
    $RemoteStateReadable
) {

    foreach ($File in $LocalStateFiles) {

        Move-ToPrivateArchive `
            $File.FullName `
            "nonprod-local-state"
    }
}
else {

    Write-Host "Local state files retained because remote backend verification did not pass."
}


# -------------------------------------------------------------------
# Archive accidental $FinalPlan artifact
# -------------------------------------------------------------------

if ($FinalPlanPresent) {

    Move-ToPrivateArchive `
        $FinalPlanPath `
        "misc"
}


# -------------------------------------------------------------------
# Safely retire stale endpoint.tf.
#
# It is first deactivated temporarily.  Terraform must still validate
# and produce a zero-change plan before it is archived permanently.
# -------------------------------------------------------------------

if (
    $EndpointStale -and
    (Test-Path $EndpointPath)
) {

    Write-Host ""
    Write-Host "Testing whether endpoint.tf can be safely retired..."

    $EndpointTestPath = "$EndpointPath.w2.8-test"

    Rename-Item `
        -LiteralPath $EndpointPath `
        -NewName (Split-Path $EndpointTestPath -Leaf)

    $EndpointRemovalPlan = Invoke-CleanTerraformPlan

    if (
        $EndpointRemovalPlan.Valid -and
        $EndpointRemovalPlan.PlanClean
    ) {

        Write-Host "endpoint.tf is stale and safe to archive."

        Move-ToPrivateArchive `
            $EndpointTestPath `
            "stale-terraform"
    }
    else {

        Write-Host "endpoint.tf removal changed Terraform behavior; restoring it."

        Rename-Item `
            -LiteralPath $EndpointTestPath `
            -NewName "endpoint.tf"

        Add-Finding `
            "REPO-ENDPOINT-RESTORE" `
            "HOLD" `
            "endpoint.tf was restored because removing it did not produce a clean Terraform plan."
    }
}


# -------------------------------------------------------------------
# Organize loose Wave evidence.
#
# JSON / hash / text evidence remains inside the project evidence
# tree.  Scripts remain available under scripts\wave2.
# -------------------------------------------------------------------

$LegacyEvidenceDirectory = Join-Path `
    $EvidenceRoot `
    "legacy"

New-Item `
    -ItemType Directory `
    -Path $LegacyEvidenceDirectory `
    -Force |
    Out-Null

$LooseEvidence = @(
    Get-ChildItem $NonProdRoot -File |
    Where-Object {
        $_.Name -match '^w2\..*\.(json|txt)$' -and
        $_.Name -notlike "w2.8-closeout*"
    }
)

foreach ($File in $LooseEvidence) {

    $Destination = Join-Path `
        $LegacyEvidenceDirectory `
        $File.Name

    if (-not (Test-Path $Destination)) {

        Move-Item `
            -LiteralPath $File.FullName `
            -Destination $Destination

        $CleanupActions += [ordered]@{
            Action      = "ORGANIZE"
            Source      = $File.FullName
            Destination = $Destination
        }
    }
}


New-Item `
    -ItemType Directory `
    -Path $ScriptArchive `
    -Force |
    Out-Null

$LooseScripts = @(
    Get-ChildItem $NonProdRoot -File |
    Where-Object {
        $_.Name -match '^w2\..*\.ps1$' -and
        $_.Name -ne (Split-Path $PSCommandPath -Leaf)
    }
)

foreach ($File in $LooseScripts) {

    $Destination = Join-Path `
        $ScriptArchive `
        $File.Name

    if (-not (Test-Path $Destination)) {

        Move-Item `
            -LiteralPath $File.FullName `
            -Destination $Destination

        $CleanupActions += [ordered]@{
            Action      = "ORGANIZE"
            Source      = $File.FullName
            Destination = $Destination
        }
    }
}


# ===================================================================
# W2.8.6 — Final reconciliation
# ===================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8.6 - FINAL WAVE 2 RECONCILIATION"
Write-Host "============================================================"
Write-Host ""

Set-Location $NonProdRoot

terraform fmt -check -recursive

if ($LASTEXITCODE -ne 0) {
    throw "Final terraform fmt check failed."
}

$FinalTerraform = Invoke-CleanTerraformPlan

if (-not $FinalTerraform.Valid) {
    throw "Final terraform validate failed."
}

if (-not $FinalTerraform.PlanClean) {
    throw "Final Terraform plan is not clean."
}


# -------------------------------------------------------------------
# Final state verification
# -------------------------------------------------------------------

$FinalState = @(
    terraform state list
)

$FinalModuleResources = @(
    $FinalState |
    Where-Object {
        $_ -like "module.network.*"
    }
)

$FinalOldRoot = @(
    $FinalState |
    Where-Object {
        $_ -match '^aws_vpc\.clinic_nonprod$' -or
        $_ -match '^aws_subnet\.(public_a|public_b|private_a|private_b)$' -or
        $_ -match '^aws_internet_gateway\.clinic_nonprod$' -or
        $_ -match '^aws_route_table\.(public|private_a|private_b)$' -or
        $_ -match '^aws_route\.public_internet$' -or
        $_ -match '^aws_route_table_association\.(public_a|public_b|private_a|private_b)$' -or
        $_ -match '^aws_security_group\.clinic_nonprod$' -or
        $_ -match '^aws_default_security_group\.clinic_nonprod$' -or
        $_ -match '^aws_vpc_security_group_egress_rule\.clinic_to_directory$' -or
        $_ -match '^aws_vpc_endpoint\.s3_gateway$'
    }
)


# -------------------------------------------------------------------
# Final Git-risk check
# -------------------------------------------------------------------

Set-Location $ProjectRoot

$FinalTracked = @(
    git ls-files |
    Where-Object {
        $_ -match $RiskPattern
    }
)

$FinalUntracked = @(
    git ls-files --others --exclude-standard |
    Where-Object {
        $_ -match $RiskPattern
    }
)


# -------------------------------------------------------------------
# Final result
# -------------------------------------------------------------------

$FinalPass = (
    $FinalTerraform.PlanClean -and
    $FinalModuleResources.Count -eq 18 -and
    $FinalOldRoot.Count -eq 0 -and
    $FinalTracked.Count -eq 0 -and
    $FinalUntracked.Count -eq 0
)

$FinalEvidence = [ordered]@{

    EvidenceId = "W2.8.6"

    Purpose = "Wave 2 Final Security and Repository Closeout"

    Timestamp = (Get-Date).ToUniversalTime().ToString("o")

    Terraform = [ordered]@{
        Valid = $FinalTerraform.Valid
        PlanExitCode = $FinalTerraform.PlanExit
        NoChanges = $FinalTerraform.PlanClean
        ModuleNetworkResourceCount = $FinalModuleResources.Count
        OldRootNetworkResourceCount = $FinalOldRoot.Count
    }

    Repository = [ordered]@{
        TrackedRiskArtifacts = @($FinalTracked)
        UntrackedRiskArtifacts = @($FinalUntracked)
        PrivateArchiveRoot = $PrivateArchiveRoot
    }

    CleanupActions = @($CleanupActions)

    AcceptedFollowUps = @(
        "Keep moved.tf through Wave 2 closure and until old state snapshots are no longer expected to be used.",
        "Keep terraform.tfvars local and ignored.",
        "Bootstrap state-backend local state is intentionally not modified by this cleanup.",
        "S3 endpoint policy is account-scoped; bucket/action least privilege is deferred until actual workload buckets exist.",
        "Directory Service controller security group remains an external AWS-managed dependency."
    )

    Result = if ($FinalPass) {
        "PASS"
    }
    else {
        "REVIEW_REQUIRED"
    }
}

$FinalEvidenceFile = Join-Path `
    $EvidenceRoot `
    "w2.8.6-wave2-closeout.json"

$FinalEvidence |
    ConvertTo-Json -Depth 30 |
    Set-Content $FinalEvidenceFile -Encoding UTF8


Write-Host ""
Write-Host "============================================================"
Write-Host " W2.8 FINAL RESULT"
Write-Host "============================================================"
Write-Host ""

Write-Host "Terraform no-change:             $($FinalTerraform.PlanClean)"
Write-Host "module.network resources:        $($FinalModuleResources.Count)"
Write-Host "Old root network resources:      $($FinalOldRoot.Count)"
Write-Host "Tracked risky artifacts:         $($FinalTracked.Count)"
Write-Host "Untracked risky artifacts:       $($FinalUntracked.Count)"
Write-Host "Cleanup actions performed:       $($CleanupActions.Count)"
Write-Host ""
Write-Host "Result:                          $($FinalEvidence.Result)"
Write-Host ""
Write-Host "Final evidence:"
Write-Host " $FinalEvidenceFile"
Write-Host ""
Write-Host "Private sensitive archive:"
Write-Host " $PrivateArchiveRoot"

if (-not $FinalPass) {
    exit 2
}

exit 0