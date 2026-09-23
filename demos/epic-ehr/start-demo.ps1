[CmdletBinding()]
param(
    [string]$SubscriptionId = '',
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$VmName = 'epicdemo-desktop-vm',
    [ValidateRange(1024, 65535)][int]$RdpPort = 53389,
    [ValidateRange(1024, 65535)][int]$TesterPort = 8765
)

$ErrorActionPreference = 'Stop'
if (-not $SubscriptionId) {
    $SubscriptionId = (& az account show --query id --output tsv --only-show-errors).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $SubscriptionId) {
        throw 'Sign in with Azure CLI or pass -SubscriptionId.'
    }
}

Write-Host 'Starting the Epic demo VM...'
& az vm start --subscription $SubscriptionId --resource-group $ResourceGroup `
    --name $VmName --only-show-errors --output none
if ($LASTEXITCODE -ne 0) {
    throw 'The Epic demo VM did not start.'
}

& (Join-Path $PSScriptRoot 'infra\enable-demo-mode.ps1') `
    -SubscriptionId $SubscriptionId -ResourceGroup $ResourceGroup -VmName $VmName

$rdpReady = Test-NetConnection -ComputerName 127.0.0.1 -Port $RdpPort `
    -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $rdpReady) {
    $connect = Join-Path $PSScriptRoot 'infra\connect.ps1'
    $arguments = @(
        '-NoProfile',
        '-NoExit',
        '-ExecutionPolicy', 'RemoteSigned',
        '-File', "`"$connect`"",
        '-SubscriptionId', "`"$SubscriptionId`"",
        '-ResourceGroup', "`"$ResourceGroup`"",
        '-LocalPort', "$RdpPort"
    ) -join ' '
    Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $PSScriptRoot |
        Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        Start-Sleep -Seconds 2
        $rdpReady = Test-NetConnection -ComputerName 127.0.0.1 -Port $RdpPort `
            -InformationLevel Quiet -WarningAction SilentlyContinue
    } while (-not $rdpReady -and [DateTime]::UtcNow -lt $deadline)
}
if (-not $rdpReady) {
    throw 'The Bastion RDP tunnel did not become ready.'
}

Start-Process mstsc.exe -ArgumentList "/v:localhost:$RdpPort"
Write-Host 'In RDP, double-click Epic Live Demo and complete the manual read-only login.'
& (Join-Path $PSScriptRoot 'service\testing.ps1') -Port $TesterPort `
    -ResourceGroup $ResourceGroup
exit $LASTEXITCODE
