$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== W2.8.1 SECURITY & CLOSURE DISCOVERY ==="
Write-Host ""

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ModuleRoot  = Join-Path $ProjectRoot "modules\network"

# ------------------------------------------------------------
# Terraform state
# ------------------------------------------------------------

$StateResources = @(
    terraform state list |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne "" }
)

if ($LASTEXITCODE -ne 0) {
    throw "terraform state list failed."
}

$ModuleNetworkResources = @(
    $StateResources |
    Where-Object { $_ -like "module.network.*" }
)

$OldRootNetworkResources = @(
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

# ------------------------------------------------------------
# Active Terraform files
# ------------------------------------------------------------

$ActiveTfFiles = @(
    Get-ChildItem -Path $PSScriptRoot -Filter "*.tf" -File |
    Sort-Object Name |
    ForEach-Object {
        [ordered]@{
            Name   = $_.Name
            Length = $_.Length
            SHA256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    }
)

$ModuleTfFiles = @()

if (Test-Path $ModuleRoot) {
    $ModuleTfFiles = @(
        Get-ChildItem -Path $ModuleRoot -Filter "*.tf" -File |
        Sort-Object Name |
        ForEach-Object {
            [ordered]@{
                Name   = $_.Name
                Length = $_.Length
                SHA256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
        }
    )
}

# ------------------------------------------------------------
# Migration / rollback artifacts
# ------------------------------------------------------------

$MovedTfPresent = Test-Path (Join-Path $PSScriptRoot "moved.tf")

$RollbackFiles = @(
    Get-ChildItem -Path $PSScriptRoot -File |
    Where-Object {
        $_.Name -like "*.pre-w2.7.5.3"
    } |
    Select-Object -ExpandProperty Name
)

$PendingFiles = @(
    Get-ChildItem -Path $PSScriptRoot -File |
    Where-Object {
        $_.Name -like "*.pending"
    } |
    Select-Object -ExpandProperty Name
)

# ------------------------------------------------------------
# Repository hygiene discovery
# No deletion or modification.
# ------------------------------------------------------------

$SensitiveArtifactPatterns = @(
    "*.tfstate",
    "*.tfstate.*",
    "*.tfplan",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12"
)

$PotentialSensitiveArtifacts = @()

foreach ($Pattern in $SensitiveArtifactPatterns) {

    $PotentialSensitiveArtifacts += @(
        Get-ChildItem `
            -Path $ProjectRoot `
            -Filter $Pattern `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
        ForEach-Object {
            $_.FullName.Replace($ProjectRoot, ".")
        }
    )
}

$TerraformDirectories = @(
    Get-ChildItem `
        -Path $ProjectRoot `
        -Directory `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq ".terraform" } |
    ForEach-Object {
        $_.FullName.Replace($ProjectRoot, ".")
    }
)

$TfvarsFiles = @(
    Get-ChildItem `
        -Path $ProjectRoot `
        -Filter "*.tfvars" `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue |
    ForEach-Object {
        $_.FullName.Replace($ProjectRoot, ".")
    }
)

# ------------------------------------------------------------
# IaC security pattern discovery
# This identifies locations; it does not alter anything.
# ------------------------------------------------------------

$Patterns = [ordered]@{
    OpenIngressIPv4    = '0\.0\.0\.0/0'
    OpenIngressIPv6    = '::/0'
    WildcardAction     = 'Action\s*=\s*".*\*"'
    WildcardResource   = 'Resource\s*=\s*"\*"'
    HardcodedSecret    = '(password|secret|token|access_key)\s*='
    PublicIpLaunch     = 'map_public_ip_on_launch\s*=\s*true'
    PreventDestroy     = 'prevent_destroy\s*=\s*true'
    MovedBlock         = '^\s*moved\s*\{'
}

$SecurityMatches = @()

$FilesToScan = @()

$FilesToScan += @(
    Get-ChildItem -Path $PSScriptRoot -Filter "*.tf" -File
)

if (Test-Path $ModuleRoot) {
    $FilesToScan += @(
        Get-ChildItem -Path $ModuleRoot -Filter "*.tf" -File
    )
}

foreach ($File in $FilesToScan) {

    $Lines = Get-Content $File.FullName

    for ($i = 0; $i -lt $Lines.Count; $i++) {

        foreach ($PatternName in $Patterns.Keys) {

            if ($Lines[$i] -match $Patterns[$PatternName]) {

                $SecurityMatches += [ordered]@{
                    Pattern = $PatternName
                    File    = $File.FullName.Replace($ProjectRoot, ".")
                    Line    = $i + 1
                    Text    = $Lines[$i].Trim()
                }
            }
        }
    }
}

# ------------------------------------------------------------
# Live AWS network verification
# ------------------------------------------------------------

$VpcId = terraform output -raw nonprod_vpc_id

if ($LASTEXITCODE -ne 0) {
    throw "Unable to retrieve nonprod_vpc_id."
}

$EndpointId = terraform output -raw nonprod_s3_gateway_endpoint_id

if ($LASTEXITCODE -ne 0) {
    throw "Unable to retrieve S3 endpoint ID."
}

$Vpc = aws ec2 describe-vpcs `
    --vpc-ids $VpcId `
    --region ap-east-1 `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw "describe-vpcs failed."
}

$Subnets = aws ec2 describe-subnets `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region ap-east-1 `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw "describe-subnets failed."
}

$RouteTables = aws ec2 describe-route-tables `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region ap-east-1 `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw "describe-route-tables failed."
}

$SecurityGroups = aws ec2 describe-security-groups `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region ap-east-1 `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw "describe-security-groups failed."
}

$Endpoint = aws ec2 describe-vpc-endpoints `
    --vpc-endpoint-ids $EndpointId `
    --region ap-east-1 `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw "describe-vpc-endpoints failed."
}

# ------------------------------------------------------------
# Evidence object
# ------------------------------------------------------------

$Evidence = [ordered]@{

    EvidenceId = "W2.8.1"

    Purpose = "Final Wave 2 Security and Closure Discovery"

    Timestamp = (Get-Date).ToUniversalTime().ToString("o")

    TerraformState = [ordered]@{
        TotalResourceCount          = $StateResources.Count
        ModuleNetworkResourceCount  = $ModuleNetworkResources.Count
        OldRootNetworkResourceCount = $OldRootNetworkResources.Count
        ModuleNetworkResources      = @($ModuleNetworkResources)
        OldRootNetworkResources     = @($OldRootNetworkResources)
    }

    SourceStructure = [ordered]@{
        ActiveEnvironmentTfFiles = @($ActiveTfFiles)
        NetworkModuleTfFiles     = @($ModuleTfFiles)
        MovedTfPresent           = $MovedTfPresent
        RollbackFiles            = @($RollbackFiles)
        PendingFiles             = @($PendingFiles)
    }

    RepositoryHygiene = [ordered]@{
        TerraformDirectories       = @($TerraformDirectories)
        TfvarsFiles                = @($TfvarsFiles)
        PotentialSensitiveArtifacts = @(
            $PotentialSensitiveArtifacts |
            Sort-Object -Unique
        )
    }

    StaticSecurityReview = [ordered]@{
        Findings = @($SecurityMatches)
    }

    LiveAws = [ordered]@{
        Vpc             = $Vpc.Vpcs
        Subnets         = $Subnets.Subnets
        RouteTables     = $RouteTables.RouteTables
        SecurityGroups  = $SecurityGroups.SecurityGroups
        S3VpcEndpoint   = $Endpoint.VpcEndpoints
    }

    Safety = [ordered]@{
        TerraformStateModified  = $false
        AwsResourcesModified    = $false
        TerraformSourceModified = $false
    }
}

$EvidenceFile = Join-Path $PSScriptRoot "w2.8.1-security-closure-discovery.json"

$Evidence |
    ConvertTo-Json -Depth 30 |
    Set-Content $EvidenceFile -Encoding UTF8

Write-Host ""
Write-Host "=== W2.8.1 DISCOVERY COMPLETE ==="
Write-Host "Module network resources:     $($ModuleNetworkResources.Count)"
Write-Host "Old root network resources:   $($OldRootNetworkResources.Count)"
Write-Host "Rollback files:               $($RollbackFiles.Count)"
Write-Host "Pending files:                $($PendingFiles.Count)"
Write-Host "Potential sensitive artifacts:$((@($PotentialSensitiveArtifacts | Sort-Object -Unique)).Count)"
Write-Host "Static review matches:        $($SecurityMatches.Count)"
Write-Host ""
Write-Host "Evidence:"
Write-Host " $EvidenceFile"
Write-Host ""
Write-Host "No AWS resources, Terraform state, or Terraform source were modified."