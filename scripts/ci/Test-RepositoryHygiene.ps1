[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TrackedFiles = @(& git ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) {
    throw "git ls-files failed."
}

$Findings = [System.Collections.Generic.List[string]]::new()
$AllowedAccountIds = @(
    "000000000001",
    "000000000002",
    "000000000099",
    "111122223333",
    "555555555555"
)
$AllowedResourceIds = @(
    "ami-0123456789abcdef0",
    "subnet-0123456789abcdef0",
    "subnet-0fedcba9876543210",
    "vpc-0123456789abcdef0"
)

foreach ($File in $TrackedFiles) {
    $Normalized = $File.Replace("\", "/")
    $Leaf = [System.IO.Path]::GetFileName($Normalized)

    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) {
        continue
    }

    if (
        $Normalized -match "(^|/)\.terraform(/|$)" -or
        $Leaf -eq "terraform.tfvars" -or
        $Leaf -match "\.tfstate(?:\..*)?$" -or
        $Leaf -match "\.tfplan$" -or
        $Leaf -match "\.(?:pem|key|p12|pfx)$" -or
        $Leaf -match "^(?:id_rsa|id_ed25519|credentials)$"
    ) {
        $Findings.Add("prohibited tracked artifact: $Normalized")
        continue
    }

    $Extension = [System.IO.Path]::GetExtension($Leaf).ToLowerInvariant()
    if ($Extension -in @(".docx", ".pdf", ".png", ".zip", ".pyc")) {
        continue
    }

    try {
        $Content = [System.IO.File]::ReadAllText((Join-Path $PWD $File))
    }
    catch {
        $Findings.Add("unable to scan tracked text file: $Normalized")
        continue
    }

    $ContentRules = [ordered]@{
        "AWS access key ID" = "(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
        "AWS secret or session token assignment" = '(?im)^\s*(?:aws_secret_access_key|aws_session_token)\s*[:=]\s*["'']?[A-Za-z0-9/+=]{20,}'
        "private key PEM block" = "(?im)^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*$"
        "Terraform state JSON structure" = '(?s)"terraform_version"\s*:.*"serial"\s*:.*"lineage"\s*:.*"resources"\s*:'
        "local Windows user path" = "(?i)[A-Za-z]:\\Users\\(?!<)[^\\\s]+\\"
        "local Unix user path" = "(?i)(?:/home|/Users)/(?!<)[A-Za-z0-9._-]+/"
    }

    foreach ($Rule in $ContentRules.GetEnumerator()) {
        if ($Content -match $Rule.Value) {
            $Findings.Add("$($Rule.Key): $Normalized")
        }
    }

    foreach ($Match in [regex]::Matches($Content, "(?<![0-9])[0-9]{12}(?![0-9])")) {
        if ($Match.Value -notin $AllowedAccountIds) {
            $Findings.Add("unapproved 12-digit account-like value: $Normalized")
            break
        }
    }

    foreach ($Match in [regex]::Matches(
        $Content,
        "(?i)(?<![A-Za-z0-9])(?:acl|ami|eni|fs|igw|nat|rtb|rtbassoc|sg|sgr|subnet|vpc|vpce|vpn|vgw|tgw)-[0-9a-f]{8,17}(?![A-Za-z0-9])"
    )) {
        if ($Match.Value.ToLowerInvariant() -notin $AllowedResourceIds) {
            $Findings.Add("unapproved AWS resource identifier: $Normalized")
            break
        }
    }
}

if ($Findings.Count -gt 0) {
    $Findings | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Repository hygiene checks passed for $($TrackedFiles.Count) tracked files."
