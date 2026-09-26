$ErrorActionPreference = "Stop"

$EvidenceFile = Join-Path $PSScriptRoot "w2.7.1-module-refactor-readiness.json"

Set-Location $PSScriptRoot

function Invoke-Capture {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    $result = & $Command 2>&1

    return @(
        $result | ForEach-Object {
            $_.ToString()
        }
    )
}

Write-Host "Collecting W2.7.1 Terraform refactor-readiness evidence..."

# -------------------------------------------------------------------
# Terraform version
# -------------------------------------------------------------------

$TerraformVersionRaw = terraform version -json | ConvertFrom-Json

# -------------------------------------------------------------------
# Current workspace
# -------------------------------------------------------------------

$Workspace = (terraform workspace show).Trim()

# -------------------------------------------------------------------
# Terraform state resource addresses
# -------------------------------------------------------------------

$StateResources = @(
    terraform state list |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne "" }
)

# -------------------------------------------------------------------
# Terraform provider/module topology
# -------------------------------------------------------------------

$Providers = Invoke-Capture {
    terraform providers
}

# -------------------------------------------------------------------
# Terraform source-file inventory
# -------------------------------------------------------------------

$TfFiles = @(
    Get-ChildItem `
        -Path $PSScriptRoot `
        -Filter "*.tf" `
        -File |
    Sort-Object Name |
    ForEach-Object {

        [ordered]@{
            Name   = $_.Name
            Length = $_.Length
            SHA256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    }
)

# -------------------------------------------------------------------
# Discover Terraform blocks without collecting full file contents
# -------------------------------------------------------------------

$ResourceBlocks = @()
$DataBlocks     = @()
$ModuleBlocks   = @()
$VariableBlocks = @()
$OutputBlocks   = @()
$MovedBlocks    = @()

foreach ($file in Get-ChildItem -Path $PSScriptRoot -Filter "*.tf" -File) {

    $lines = Get-Content $file.FullName

    for ($i = 0; $i -lt $lines.Count; $i++) {

        $line = $lines[$i]

        if ($line -match '^\s*resource\s+"([^"]+)"\s+"([^"]+)"') {
            $ResourceBlocks += [ordered]@{
                File         = $file.Name
                Line         = $i + 1
                ResourceType = $Matches[1]
                ResourceName = $Matches[2]
                Address      = "$($Matches[1]).$($Matches[2])"
            }
        }

        if ($line -match '^\s*data\s+"([^"]+)"\s+"([^"]+)"') {
            $DataBlocks += [ordered]@{
                File     = $file.Name
                Line     = $i + 1
                DataType = $Matches[1]
                DataName = $Matches[2]
                Address  = "data.$($Matches[1]).$($Matches[2])"
            }
        }

        if ($line -match '^\s*module\s+"([^"]+)"') {
            $ModuleBlocks += [ordered]@{
                File       = $file.Name
                Line       = $i + 1
                ModuleName = $Matches[1]
            }
        }

        if ($line -match '^\s*variable\s+"([^"]+)"') {
            $VariableBlocks += [ordered]@{
                File         = $file.Name
                Line         = $i + 1
                VariableName = $Matches[1]
            }
        }

        if ($line -match '^\s*output\s+"([^"]+)"') {
            $OutputBlocks += [ordered]@{
                File       = $file.Name
                Line       = $i + 1
                OutputName = $Matches[1]
            }
        }

        if ($line -match '^\s*moved\s*\{') {
            $MovedBlocks += [ordered]@{
                File = $file.Name
                Line = $i + 1
            }
        }
    }
}

# -------------------------------------------------------------------
# Detect potentially hard-coded AWS infrastructure identifiers
# Do not collect arbitrary source-code contents.
# -------------------------------------------------------------------

$HardcodedIds = @()

$AwsIdPatterns = @(
    'vpc-[0-9a-f]+',
    'subnet-[0-9a-f]+',
    'rtb-[0-9a-f]+',
    'sg-[0-9a-f]+',
    'igw-[0-9a-f]+',
    'vpce-[0-9a-f]+',
    'pl-[0-9a-f]+'
)

foreach ($file in Get-ChildItem -Path $PSScriptRoot -Filter "*.tf" -File) {

    $lines = Get-Content $file.FullName

    for ($i = 0; $i -lt $lines.Count; $i++) {

        foreach ($pattern in $AwsIdPatterns) {

            $matches = [regex]::Matches(
                $lines[$i],
                $pattern,
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )

            foreach ($match in $matches) {

                $HardcodedIds += [ordered]@{
                    File = $file.Name
                    Line = $i + 1
                    Id   = $match.Value
                }
            }
        }
    }
}

# -------------------------------------------------------------------
# Categorise current root resources
# -------------------------------------------------------------------

$NetworkStateResources = @(
    $StateResources |
    Where-Object {
        $_ -match '^aws_vpc\.' -or
        $_ -match '^aws_subnet\.' -or
        $_ -match '^aws_internet_gateway\.' -or
        $_ -match '^aws_route_table\.' -or
        $_ -match '^aws_route_table_association\.' -or
        $_ -match '^aws_route\.' -or
        $_ -match '^aws_security_group\.' -or
        $_ -match '^aws_default_security_group\.' -or
        $_ -match '^aws_vpc_security_group_' -or
        $_ -match '^aws_vpc_endpoint\.'
    }
)

$NonNetworkStateResources = @(
    $StateResources |
    Where-Object {
        $NetworkStateResources -notcontains $_
    }
)

# -------------------------------------------------------------------
# Evidence object
# -------------------------------------------------------------------

$Evidence = [ordered]@{

    EvidenceId = "W2.7.1"

    Purpose = "Network Module Refactor Readiness Discovery"

    Timestamp = (Get-Date).ToUniversalTime().ToString("o")

    WorkingDirectory = $PSScriptRoot

    Terraform = [ordered]@{
        Version   = $TerraformVersionRaw.terraform_version
        Platform  = $TerraformVersionRaw.platform
        Workspace = $Workspace
    }

    SourceFiles = $TfFiles

    CurrentConfiguration = [ordered]@{
        ResourceBlocks = @($ResourceBlocks)
        DataBlocks     = @($DataBlocks)
        ModuleBlocks   = @($ModuleBlocks)
        VariableBlocks = @($VariableBlocks)
        OutputBlocks   = @($OutputBlocks)
        MovedBlocks    = @($MovedBlocks)
    }

    TerraformState = [ordered]@{
        TotalResourceCount      = $StateResources.Count
        AllResources            = @($StateResources)
        NetworkResourceCount    = $NetworkStateResources.Count
        NetworkResources        = @($NetworkStateResources)
        NonNetworkResourceCount = $NonNetworkStateResources.Count
        NonNetworkResources     = @($NonNetworkStateResources)
    }

    ExistingModuleCount = $ModuleBlocks.Count

    HardcodedAwsIdentifiers = @($HardcodedIds)

    ProviderTopology = @($Providers)

    Safety = [ordered]@{
        TerraformStateModified = $false
        AwsResourcesModified   = $false
        TerraformSourceModified = $false
    }
}

$Evidence |
    ConvertTo-Json -Depth 20 |
    Set-Content $EvidenceFile -Encoding UTF8

Write-Host ""
Write-Host "=== W2.7.1 DISCOVERY COMPLETE ==="
Write-Host "Terraform version:       $($TerraformVersionRaw.terraform_version)"
Write-Host "Workspace:               $Workspace"
Write-Host "TF source files:         $($TfFiles.Count)"
Write-Host "State resources:         $($StateResources.Count)"
Write-Host "Network resources:       $($NetworkStateResources.Count)"
Write-Host "Existing modules:        $($ModuleBlocks.Count)"
Write-Host "Existing moved blocks:   $($MovedBlocks.Count)"
Write-Host "Hard-coded AWS IDs:      $($HardcodedIds.Count)"
Write-Host ""
Write-Host "Evidence:"
Write-Host " $EvidenceFile"
Write-Host ""
Write-Host "No AWS resources, Terraform state, or Terraform source files were modified."