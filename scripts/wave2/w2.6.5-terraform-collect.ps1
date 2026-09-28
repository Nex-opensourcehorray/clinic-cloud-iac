terraform fmt -check
if ($LASTEXITCODE -ne 0) {
    throw "terraform fmt -check failed."
}

terraform validate
if ($LASTEXITCODE -ne 0) {
    throw "terraform validate failed."
}

terraform plan -detailed-exitcode -no-color `
    | Tee-Object -FilePath "..\..\evidence\W2.6.5\w2.6.5-terraform-plan.txt"

$PlanExitCode = $LASTEXITCODE

Set-Location ..\..

$PlanExitCode |
    Set-Content ".\evidence\W2.6.5\w2.6.5-terraform-plan-exitcode.txt"

Get-FileHash `
    ".\evidence\W2.6.5\w2.6.5-terraform-plan.txt" `
    -Algorithm SHA256 |
    Format-List |
    Out-File ".\evidence\W2.6.5\w2.6.5-terraform-plan.sha256.txt"

Write-Host "Terraform detailed exit code: $PlanExitCode"