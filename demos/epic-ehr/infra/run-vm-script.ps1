[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ScriptPath,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9-]+$')][string]$CommandName,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$VmName = 'epicdemo-desktop-vm',
    [string]$Location = 'swedencentral',
    [hashtable]$ProtectedParameters = @{},
    [switch]$StartOnly,
    [switch]$WithAdminCredential
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stateRoot = Join-Path $repoRoot ".azure\$ResourceGroup"
if (-not (Test-Path -LiteralPath $stateRoot)) { throw 'Run deploy.ps1 first to create the protected local state directory.' }
$properties = @{
    source = @{ script = Get-Content -LiteralPath $ScriptPath -Raw }
    timeoutInSeconds = 1800
    asyncExecution = $false
    protectedParameters = @(
        foreach ($item in $ProtectedParameters.GetEnumerator()) {
            @{ name = $item.Key; value = [string]$item.Value }
        }
    )
}
if ($WithAdminCredential) {
    $credential = Import-Clixml -LiteralPath (Join-Path $stateRoot 'vm-admin.credential.xml')
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $passwordHash = [Convert]::ToBase64String($hash.ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($credential.GetNetworkCredential().Password)
        ))
    } finally { $hash.Dispose() }
    $properties.protectedParameters += @(
        @{ name = 'AdminUser'; value = $credential.UserName },
        @{ name = 'AdminPassword'; value = $credential.GetNetworkCredential().Password },
        @{ name = 'ExpectedPasswordHash'; value = $passwordHash }
    )
}
$bodyPath = Join-Path $stateRoot ("command-" + [guid]::NewGuid().ToString('N') + '.json')
$vmId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Compute/virtualMachines/$VmName"
try {
    @{ location = $Location; properties = $properties } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $bodyPath -Encoding UTF8
    & az rest --method put --url "https://management.azure.com$vmId/runCommands/${CommandName}?api-version=2024-03-01" `
        --body "@$bodyPath" --only-show-errors --query properties.provisioningState --output tsv
    if ($LASTEXITCODE -ne 0) { throw 'Could not start managed VM Run Command.' }
} finally {
    $properties = $null
    if (Test-Path -LiteralPath $bodyPath) { Remove-Item -LiteralPath $bodyPath -Force }
}
if ($StartOnly) { return }
$deadline = [DateTime]::UtcNow.AddMinutes(32)
do {
    $raw = & az vm run-command show --subscription $SubscriptionId --resource-group $ResourceGroup `
        --vm-name $VmName --run-command-name $CommandName --expand instanceView `
        --query instanceView --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect managed VM Run Command.' }
    $status = $raw | ConvertFrom-Json
    if ($status.executionState -in @('Succeeded', 'Failed', 'Canceled', 'TimedOut')) {
        if ($status.output) { Write-Output $status.output }
        if ($status.error) { Write-Warning $status.error }
        if ($status.executionState -ne 'Succeeded' -or $status.exitCode -ne 0) {
            throw "VM command failed: $($status.executionState), exit code $($status.exitCode)."
        }
        return
    }
    Start-Sleep -Seconds 10
} while ([DateTime]::UtcNow -lt $deadline)
throw "VM command did not finish within the deadline. Inspect $CommandName before retrying."
