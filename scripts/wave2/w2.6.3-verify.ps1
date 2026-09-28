$ErrorActionPreference = "Stop"

$Region = "ap-east-1"
$EvidenceFile = "w2.6.3-s3-endpoint-closeout.json"
$FinalPlan = "w2.6.3-s3-endpoint-final.tfplan"

Write-Host "[1/5] Reading Terraform state..."

$TfStateRaw = terraform show -json
if ($LASTEXITCODE -ne 0) {
    throw "terraform show -json failed."
}
$TfState = ($TfStateRaw -join "`n") | ConvertFrom-Json

function Get-TfResources {
    param($Module)

    $resources = @()

    if ($Module.resources) {
        $resources += $Module.resources
    }

    if ($Module.child_modules) {
        foreach ($child in $Module.child_modules) {
            $resources += Get-TfResources -Module $child
        }
    }

    return $resources
}

$Resources = Get-TfResources -Module $TfState.values.root_module

$EndpointTf = $Resources |
    Where-Object { $_.address -eq "aws_vpc_endpoint.s3_gateway" }

$PrivateA = $Resources |
    Where-Object { $_.address -eq "aws_route_table.private_a" }

$PrivateB = $Resources |
    Where-Object { $_.address -eq "aws_route_table.private_b" }

$Public = $Resources |
    Where-Object { $_.address -eq "aws_route_table.public" }

if (-not $EndpointTf) { throw "S3 endpoint not found in Terraform state." }
if (-not $PrivateA)   { throw "private_a route table not found in Terraform state." }
if (-not $PrivateB)   { throw "private_b route table not found in Terraform state." }
if (-not $Public)     { throw "public route table not found in Terraform state." }

$EndpointId = $EndpointTf.values.id

Write-Host "[2/5] Reading AWS endpoint..."

$EndpointRaw = aws ec2 describe-vpc-endpoints `
    --vpc-endpoint-ids $EndpointId `
    --region $Region `
    --output json `
    --no-cli-pager

if ($LASTEXITCODE -ne 0) {
    throw "describe-vpc-endpoints failed."
}

$EndpointAws = (($EndpointRaw -join "`n") | ConvertFrom-Json).VpcEndpoints[0]

Write-Host "[3/5] Reading route tables..."

$RouteTableRaw = aws ec2 describe-route-tables `
    --route-table-ids `
        $PrivateA.values.id `
        $PrivateB.values.id `
        $Public.values.id `
    --region $Region `
    --output json `
    --no-cli-pager

if ($LASTEXITCODE -ne 0) {
    throw "describe-route-tables failed."
}

$RouteTables = (($RouteTableRaw -join "`n") | ConvertFrom-Json).RouteTables

function Test-EndpointRoute {
    param(
        $RouteTable,
        $EndpointId
    )

    return @(
        $RouteTable.Routes |
        Where-Object {
            $_.GatewayId -eq $EndpointId -and
            $_.DestinationPrefixListId
        }
    ).Count -gt 0
}

$PrivateARt = $RouteTables |
    Where-Object RouteTableId -eq $PrivateA.values.id

$PrivateBRt = $RouteTables |
    Where-Object RouteTableId -eq $PrivateB.values.id

$PublicRt = $RouteTables |
    Where-Object RouteTableId -eq $Public.values.id

$PrivateAHasEndpoint = Test-EndpointRoute $PrivateARt $EndpointId
$PrivateBHasEndpoint = Test-EndpointRoute $PrivateBRt $EndpointId
$PublicHasEndpoint   = Test-EndpointRoute $PublicRt $EndpointId

Write-Host "[4/5] Running final Terraform drift check..."

terraform plan `
    -detailed-exitcode `
    -out=$FinalPlan

$PlanExitCode = $LASTEXITCODE

$NoTerraformDrift = ($PlanExitCode -eq 0)

if ($PlanExitCode -eq 1) {
    throw "Terraform plan failed."
}

Write-Host "[5/5] Building closeout JSON..."

$ExpectedPrivateRouteTables = @(
    $PrivateA.values.id,
    $PrivateB.values.id
) | Sort-Object

$ActualEndpointRouteTables = @(
    $EndpointAws.RouteTableIds
) | Sort-Object

$PrivateScopeMatches =
    (($ExpectedPrivateRouteTables -join ",") -eq
     ($ActualEndpointRouteTables -join ","))

$Result = [ordered]@{
    Evidence          = "W2.6.3 S3 Gateway Endpoint Closeout"
    Region            = $Region
    EndpointId        = $EndpointId
    EndpointState     = $EndpointAws.State
    EndpointType      = $EndpointAws.VpcEndpointType
    ServiceName       = $EndpointAws.ServiceName
    VpcId             = $EndpointAws.VpcId

    Terraform = [ordered]@{
        ResourceAddress = $EndpointTf.address
        Managed          = $true
        PlanExitCode     = $PlanExitCode
        NoDrift          = $NoTerraformDrift
    }

    RouteTableScope = [ordered]@{
        PrivateA = [ordered]@{
            RouteTableId = $PrivateA.values.id
            EndpointRoutePresent = $PrivateAHasEndpoint
        }

        PrivateB = [ordered]@{
            RouteTableId = $PrivateB.values.id
            EndpointRoutePresent = $PrivateBHasEndpoint
        }

        Public = [ordered]@{
            RouteTableId = $Public.values.id
            EndpointRoutePresent = $PublicHasEndpoint
        }

        EndpointReportedRouteTables = $ActualEndpointRouteTables
        ExpectedPrivateRouteTables  = $ExpectedPrivateRouteTables
        PrivateScopeExactlyMatches  = $PrivateScopeMatches
    }

    Gate = [ordered]@{
        EndpointAvailable =
            ($EndpointAws.State -eq "available")

        CorrectType =
            ($EndpointAws.VpcEndpointType -eq "Gateway")

        CorrectService =
            ($EndpointAws.ServiceName -eq "com.amazonaws.$Region.s3")

        PrivateAConnected =
            $PrivateAHasEndpoint

        PrivateBConnected =
            $PrivateBHasEndpoint

        PublicExcluded =
            (-not $PublicHasEndpoint)

        NoTerraformDrift =
            $NoTerraformDrift

        OverallPass = (
            ($EndpointAws.State -eq "available") -and
            ($EndpointAws.VpcEndpointType -eq "Gateway") -and
            ($EndpointAws.ServiceName -eq "com.amazonaws.$Region.s3") -and
            $PrivateAHasEndpoint -and
            $PrivateBHasEndpoint -and
            (-not $PublicHasEndpoint) -and
            $PrivateScopeMatches -and
            $NoTerraformDrift
        )
    }
}

$Result |
    ConvertTo-Json -Depth 8 |
    Set-Content -Encoding UTF8 $EvidenceFile

Write-Host ""
Write-Host "Evidence written to: $EvidenceFile"
Write-Host ""
$Result.Gate | Format-List