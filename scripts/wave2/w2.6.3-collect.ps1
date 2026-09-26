$Region = "ap-east-1"

$VpcId = terraform output -raw nonprod_vpc_id

$PrivateA = terraform output -json nonprod_subnet_ids |
    ConvertFrom-Json |
    Select-Object -ExpandProperty private_a

$PrivateB = terraform output -json nonprod_subnet_ids |
    ConvertFrom-Json |
    Select-Object -ExpandProperty private_b

$Caller = aws sts get-caller-identity `
    --output json |
    ConvertFrom-Json

$Vpc = aws ec2 describe-vpcs `
    --vpc-ids $VpcId `
    --region $Region `
    --output json `
    --no-cli-pager |
    ConvertFrom-Json

$RouteTables = aws ec2 describe-route-tables `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region $Region `
    --output json `
    --no-cli-pager |
    ConvertFrom-Json

$Endpoints = aws ec2 describe-vpc-endpoints `
    --filters "Name=vpc-id,Values=$VpcId" `
    --region $Region `
    --output json `
    --no-cli-pager |
    ConvertFrom-Json

$S3Services = aws ec2 describe-vpc-endpoint-services `
    --region $Region `
    --filters "Name=service-name,Values=com.amazonaws.$Region.s3" `
    --output json `
    --no-cli-pager |
    ConvertFrom-Json

$Evidence = [ordered]@{
    EvidenceBlock = "W2.6.3"
    Purpose       = "S3 Gateway Endpoint pre-adoption baseline"
    CollectedUTC  = (Get-Date).ToUniversalTime().ToString("o")

    Caller = $Caller

    Target = @{
        Region          = $Region
        VpcId           = $VpcId
        PrivateSubnetA  = $PrivateA
        PrivateSubnetB  = $PrivateB
        S3ServiceName   = "com.amazonaws.$Region.s3"
    }

    Vpc = $Vpc.Vpcs

    ExistingVpcEndpoints = $Endpoints.VpcEndpoints

    S3EndpointService = @{
        ServiceNames = $S3Services.ServiceNames
    }

    RouteTables = @(
        $RouteTables.RouteTables | ForEach-Object {
            [ordered]@{
                RouteTableId = $_.RouteTableId

                Associations = @(
                    $_.Associations | ForEach-Object {
                        @{
                            AssociationId = $_.RouteTableAssociationId
                            SubnetId      = $_.SubnetId
                            Main          = $_.Main
                        }
                    }
                )

                Routes = @(
                    $_.Routes | ForEach-Object {
                        @{
                            DestinationCidrBlock    = $_.DestinationCidrBlock
                            DestinationPrefixListId = $_.DestinationPrefixListId
                            GatewayId               = $_.GatewayId
                            NatGatewayId            = $_.NatGatewayId
                            State                   = $_.State
                        }
                    }
                )
            }
        }
    )
}

$Evidence |
    ConvertTo-Json -Depth 12 |
    Set-Content ".\w2.6.3-s3-endpoint-prechange.json" -Encoding UTF8

Write-Host ""
Write-Host "W2.6.3 evidence written to:"
Write-Host "  w2.6.3-s3-endpoint-prechange.json"
Write-Host ""
Write-Host "Existing VPC endpoints: $($Endpoints.VpcEndpoints.Count)"
Write-Host "S3 service discovered: $($S3Services.ServiceNames.Count)"
$UniqueS3Services = @(
    $S3Services.ServiceNames |
    Sort-Object -Unique
)

Write-Host "Unique S3 endpoint services: $($UniqueS3Services.Count)"