$ErrorActionPreference = "Stop"

$SourceFile = Join-Path $PSScriptRoot "w2.6.4-interface-endpoint-readiness.json"
$EvidenceDir = Join-Path $PSScriptRoot "evidence\W2.6.5"

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null

if (-not (Test-Path $SourceFile)) {
    throw "Missing W2.6.4 evidence: $SourceFile"
}

$W264 = Get-Content $SourceFile -Raw | ConvertFrom-Json

$PrivateEc2Count = @($W264.PrivateEc2Instances).Count
$SsmManagedNodeCount = @($W264.SsmManagedNodes).Count
$ExistingInterfaceEndpointCount = @(
    $W264.ExistingVpcEndpoints |
    Where-Object { $_.VpcEndpointType -eq "Interface" }
).Count

$DecisionMatrix = foreach ($Service in $W264.CandidateInterfaceEndpointServices) {

    $Decision = "DEFER"
    $RequiredNow = $false

    $Reason = switch ($Service.ShortName) {

        "ssm" {
            "No private EC2 instance or SSM managed node currently requires private Systems Manager API connectivity."
        }

        "ssmmessages" {
            "No SSM managed node currently requires the Systems Manager message channel."
        }

        "ec2messages" {
            "No SSM managed node exists. Retain only as a future compatibility consideration; do not deploy solely because the service is available."
        }

        "logs" {
            "No private workload currently requires direct private CloudWatch Logs API connectivity."
        }

        "kms" {
            "Existing AWS service encryption does not by itself justify a KMS interface endpoint. Deploy only when a VPC workload must call the KMS API privately."
        }

        "sts" {
            "No private workload currently demonstrates a requirement for direct private STS API access."
        }

        "secretsmanager" {
            "No private workload currently demonstrates a requirement for private Secrets Manager API access."
        }

        default {
            "No demonstrated workload dependency."
        }
    }

    [ordered]@{
        ShortName       = $Service.ShortName
        ServiceName     = $Service.ServiceName
        ServiceAvailable = $Service.Available
        RequiredNow     = $RequiredNow
        Decision        = $Decision
        Reason          = $Reason
    }
}

$RequiredNowCount = @(
    $DecisionMatrix |
    Where-Object { $_.RequiredNow -eq $true }
).Count

$Result = if (
    $PrivateEc2Count -eq 0 -and
    $SsmManagedNodeCount -eq 0 -and
    $RequiredNowCount -eq 0
) {
    "PASS"
}
else {
    "REVIEW_REQUIRED"
}

$Evidence = [ordered]@{
    EvidenceId = "W2.6.5"

    Purpose = "Interface Endpoint Justification Decision"

    Timestamp = (Get-Date).ToUniversalTime().ToString("o")

    Region = $W264.Region

    VpcId = $W264.Terraform.VpcId

    SourceEvidence = [ordered]@{
        File = $SourceFile
        SHA256 = (Get-FileHash $SourceFile -Algorithm SHA256).Hash
    }

    CurrentState = [ordered]@{
        PrivateSubnetCount = @($W264.PrivateSubnets).Count
        PrivateEc2InstanceCount = $PrivateEc2Count
        SsmManagedNodeCount = $SsmManagedNodeCount
        ExistingInterfaceEndpointCount = $ExistingInterfaceEndpointCount
        ExistingVpcEndpointCount = @($W264.ExistingVpcEndpoints).Count
    }

    InterfaceEndpointDecision = [ordered]@{
        RequiredNowCount = $RequiredNowCount
        ImplementationDecision = "DEFER_INTERFACE_ENDPOINTS_UNTIL_DEMONSTRATED_WORKLOAD_NEED"
        EndpointResourcesToCreate = 0
    }

    ServiceMatrix = @($DecisionMatrix)

    Result = $Result
}

$JsonFile = Join-Path $EvidenceDir "w2.6.5-interface-endpoint-decision.json"
$HashFile = Join-Path $EvidenceDir "w2.6.5-interface-endpoint-decision.sha256.txt"

$Evidence |
    ConvertTo-Json -Depth 10 |
    Set-Content $JsonFile -Encoding UTF8

$Hash = Get-FileHash $JsonFile -Algorithm SHA256

"$($Hash.Hash)  w2.6.5-interface-endpoint-decision.json" |
    Set-Content $HashFile -Encoding ASCII

Write-Host ""
Write-Host "=== W2.6.5 COMPLETE ==="
Write-Host "Result:                    $Result"
Write-Host "Private EC2 instances:     $PrivateEc2Count"
Write-Host "SSM managed nodes:         $SsmManagedNodeCount"
Write-Host "Interface endpoints now:   $ExistingInterfaceEndpointCount"
Write-Host "Interface endpoints needed:$RequiredNowCount"
Write-Host ""
Write-Host "Evidence:"
Write-Host " $JsonFile"
Write-Host " $HashFile"