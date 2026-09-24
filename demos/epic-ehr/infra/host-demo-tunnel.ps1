[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9-]+(?:\.[a-z0-9]+)?$')]
    [string]$TunnelId,
    [string]$HostToken = '',
    [ValidateRange(1, 65535)][int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
if ($HostToken -match "[`r`n]") {
    throw 'Tunnel host token is invalid.'
}

$runtime = 'C:\EpicDemo\remote'
$runner = Join-Path $runtime 'host-demo-tunnel.ps1'
$tokenPath = Join-Path $runtime 'host-token.txt'
$devtunnel = 'C:\DemoTools\devtunnel\devtunnel.exe'
$taskName = 'EpicDemoStableTunnel'
if (-not (Test-Path -LiteralPath $devtunnel)) {
    throw 'Install the dev tunnel tooling first.'
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
& icacls.exe $runtime '/inheritance:r' '/grant:r' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not restrict the remote tunnel state to SYSTEM.'
}
if ($HostToken) {
    $HostToken | Set-Content -LiteralPath $tokenPath -Encoding UTF8 -NoNewline
}
if (-not (Test-Path -LiteralPath $tokenPath)) {
    throw 'No tunnel host token is available. Provision it once before enabling demo mode.'
}

@'
# Runs forever: waits for the API (it only starts after the demo user logs on)
# and re-hosts the tunnel whenever devtunnel exits.
$ErrorActionPreference = 'Continue'
while ($true) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:__PORT__/healthz' -TimeoutSec 2
    } catch { $health = $null }
    if ($health.status -eq 'ok') {
        $token = Get-Content -LiteralPath 'C:\EpicDemo\remote\host-token.txt' -Raw
        & 'C:\DemoTools\devtunnel\devtunnel.exe' host '__TUNNEL_ID__' --access-token $token
        Start-Sleep -Seconds 10
    } else {
        Start-Sleep -Seconds 5
    }
}
'@.Replace('__TUNNEL_ID__', $TunnelId).Replace('__PORT__', "$Port") |
    Set-Content -LiteralPath $runner -Encoding UTF8

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument (
    "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
    -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtStartup
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal `
    -Settings $settings -Trigger $trigger -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Stable authenticated tunnel task installed for $TunnelId on port $Port."
