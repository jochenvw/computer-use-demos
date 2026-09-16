[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$Location = 'swedencentral',
    [ValidatePattern('^[a-z][a-z0-9]{2,11}$')][string]$Prefix = 'epicdemo',
    [string]$VmSize = 'Standard_D4as_v5',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'Run this deployment helper on Windows: local credentials use user-bound DPAPI encryption.'
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw 'Install Azure CLI and run az login before deploying.'
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stateRoot = Join-Path $repoRoot ".azure\$ResourceGroup"
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
$acl = Get-Acl -LiteralPath $stateRoot
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().User,
    [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
)) {
    $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new(
        $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'
    ))
}
Set-Acl -LiteralPath $stateRoot -AclObject $acl
$credentialPath = Join-Path $stateRoot 'vm-admin.credential.xml'
if (Test-Path -LiteralPath $credentialPath) {
    $credential = Import-Clixml -LiteralPath $credentialPath
    if ($credential -isnot [System.Management.Automation.PSCredential]) {
        throw 'The stored VM credential is invalid.'
    }
} else {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $secret = [Convert]::ToBase64String($bytes) + 'aA1!'
    $credential = [pscredential]::new('demoadmin', (ConvertTo-SecureString $secret -AsPlainText -Force))
    $credential | Export-Clixml -LiteralPath $credentialPath
    $secret = $null
}

$parameterPath = Join-Path $stateRoot ("parameters-" + [guid]::NewGuid().ToString('N') + '.json')
try {
    $parameters = @{
        '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters = @{
            location = @{ value = $Location }
            prefix = @{ value = $Prefix }
            vmSize = @{ value = $VmSize }
            adminUsername = @{ value = $credential.UserName }
            adminPassword = @{ value = $credential.GetNetworkCredential().Password }
        }
    }
    $parameters | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $parameterPath -Encoding UTF8
    & az group create --subscription $SubscriptionId --name $ResourceGroup --location $Location `
        --tags workload=epic-demo environment=development --only-show-errors --output none
    if ($LASTEXITCODE -ne 0) { throw 'Resource group creation failed.' }
    & az deployment group validate --subscription $SubscriptionId --resource-group $ResourceGroup `
        --template-file (Join-Path $PSScriptRoot 'main.bicep') --parameters "@$parameterPath" `
        --only-show-errors --query properties.provisioningState --output tsv
    if ($LASTEXITCODE -ne 0) { throw 'Azure deployment validation failed.' }
    if ($ValidateOnly) {
        Write-Host 'Template validation completed; no VM or network resources were deployed.'
        return
    }
    & az deployment group create --subscription $SubscriptionId --resource-group $ResourceGroup `
        --name 'epic-desktop' --template-file (Join-Path $PSScriptRoot 'main.bicep') `
        --parameters "@$parameterPath" --only-show-errors --query properties.outputs --output json
    if ($LASTEXITCODE -ne 0) { throw 'Azure deployment failed; inspect the deployment operations before retrying.' }
    Write-Host "Encrypted VM credential: $credentialPath"
    Write-Host 'Use connect.ps1 to open the Bastion tunnel. No password was written to console or Git.'
} finally {
    $parameters = $null
    if (Test-Path -LiteralPath $parameterPath) {
        Remove-Item -LiteralPath $parameterPath -Force
    }
}
