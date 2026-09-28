[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = [System.IO.Compression.ZipFile]::Open(
    $OutputPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)

try {
    Get-ChildItem -LiteralPath $sourcePath -Recurse -File |
        Where-Object {
            $_.Extension -ne ".pyc" -and
            $_.FullName -notmatch "[\\/]__pycache__[\\/]"
        } |
        ForEach-Object {
            $entryName = $_.FullName.Substring($sourcePath.Length).TrimStart("\")
            $entryName = $entryName.Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $_.FullName,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
}
finally {
    if ($null -ne $archive) {
        $archive.Dispose()
    }
}

Write-Output $OutputPath
