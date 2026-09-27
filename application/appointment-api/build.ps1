[CmdletBinding()]
param(
    [string]$OutputPath
)

$ScriptRoot = Split-Path -Parent $PSCommandPath

if ([string]::IsNullOrWhiteSpace($ScriptRoot)) {
    $ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if ([string]::IsNullOrWhiteSpace($ScriptRoot)) {
    throw "Unable to determine build.ps1 script directory."
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $ScriptRoot "dist\appointment-api.zip"
}

$sourcePath = Join-Path $ScriptRoot "src"
$outputDirectory = Split-Path -Parent $OutputPath

if (-not (Test-Path -LiteralPath $sourcePath)) {
    throw "Application source directory not found: $sourcePath"
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

Compress-Archive -Path (Join-Path $sourcePath "*") -DestinationPath $OutputPath
Write-Output $OutputPath
