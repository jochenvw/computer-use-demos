[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$VmName = 'epicdemo-desktop-vm'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stateRoot = Join-Path $repoRoot ".azure\$ResourceGroup"
$tunnelIdPath = Join-Path $stateRoot 'active-tunnel-id.txt'
$hostTokenPath = Join-Path $stateRoot 'vm-tunnel-host-token.xml'
$originPath = Join-Path $stateRoot 'vm-tunnel-origin.txt'
$connectTokenPath = Join-Path $stateRoot 'vm-tunnel-connect-token.xml'
$apiTokenPath = Join-Path $stateRoot 'vm-api-token.xml'
foreach ($path in @(
    $tunnelIdPath, $originPath, $apiTokenPath
)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Protected demo state is incomplete: $path"
    }
}
if (-not (Get-Command devtunnel -ErrorAction SilentlyContinue)) {
    throw 'Install the dev tunnel CLI and sign in before enabling demo mode.'
}

$tunnelId = (Get-Content -LiteralPath $tunnelIdPath -Raw).Trim()
$tokenJson = & devtunnel token $tunnelId --scopes host --json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ($tokenJson -join [Environment]::NewLine)
}
$hostToken = (($tokenJson -join [Environment]::NewLine) | ConvertFrom-Json).token
$tokenJson = & devtunnel token $tunnelId --scopes connect --json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ($tokenJson -join [Environment]::NewLine)
}
$connectToken = (($tokenJson -join [Environment]::NewLine) | ConvertFrom-Json).token
if ([string]::IsNullOrWhiteSpace($hostToken) -or
    [string]::IsNullOrWhiteSpace($connectToken)) {
    throw 'The dev tunnel CLI returned an empty access token.'
}
ConvertTo-SecureString $hostToken -AsPlainText -Force |
    Export-Clixml -LiteralPath $hostTokenPath
ConvertTo-SecureString $connectToken -AsPlainText -Force |
    Export-Clixml -LiteralPath $connectTokenPath

$runVmScript = Join-Path $PSScriptRoot 'run-vm-script.ps1'
$tunnelParameters = @{ TunnelId = $tunnelId; HostToken = $hostToken }
try {
    & $runVmScript `
        -SubscriptionId $SubscriptionId `
        -ResourceGroup $ResourceGroup `
        -VmName $VmName `
        -ScriptPath (Join-Path $PSScriptRoot 'host-demo-tunnel.ps1') `
        -CommandName 'host-demo-tunnel' `
        -ProtectedParameters $tunnelParameters
} finally {
    $hostToken = $null
    $connectToken = $null
    $tokenJson = $null
    $tunnelParameters = $null
}

$launcherContent = Get-Content -LiteralPath (
    Join-Path $PSScriptRoot '..\service\live.ps1'
) -Raw
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $launcherHash = [BitConverter]::ToString(
        $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($launcherContent))
    ).Replace('-', '')
} finally {
    $sha256.Dispose()
}
try {
    & $runVmScript `
        -SubscriptionId $SubscriptionId `
        -ResourceGroup $ResourceGroup `
        -VmName $VmName `
        -ScriptPath (Join-Path $PSScriptRoot 'install-live-launcher.ps1') `
        -CommandName 'install-live-launcher' `
        -ProtectedParameters @{
            LauncherContent = $launcherContent
            ExpectedSha256 = $launcherHash
        }
} finally {
    $launcherContent = $null
}
Write-Output (
    'One-click demo mode enabled. The local tester will use the protected ' +
    'tunnel origin and credentials automatically.'
)
