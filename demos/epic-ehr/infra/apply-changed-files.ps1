[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{32}$')][string]$TransferId,
    [Parameter(Mandatory)][ValidateRange(1, 1024)][int]$PartCount,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ArchiveSha256
)
$ErrorActionPreference = 'Stop'
$staging = Join-Path 'C:\EpicDemo\.staging' $TransferId
$archive = Join-Path $staging 'changed.zip'
$service = 'C:\EpicDemo\service'
try {
    $parts = @(Get-ChildItem -LiteralPath $staging -Filter '*.part' -File | Sort-Object Name)
    if ($parts.Count -ne $PartCount) { throw "Expected $PartCount parts; found $($parts.Count)." }
    $out = [IO.File]::Open($archive, 'Create', 'Write', 'None')
    try { foreach ($p in $parts) { $b = [IO.File]::ReadAllBytes($p.FullName); $out.Write($b, 0, $b.Length) } }
    finally { $out.Dispose() }
    if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $ArchiveSha256.ToUpperInvariant()) { throw 'Archive hash mismatch.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $service -Force
} finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}

$envPath = Join-Path $service '.env'
$lines = [Collections.Generic.List[string]]::new()
$lines.AddRange([string[]](Get-Content -LiteralPath $envPath))
function Set-EnvValue([string]$Name, [string]$Value) {
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        if ($lines[$i] -match ('^\s*' + [regex]::Escape($Name) + '=')) { $lines.RemoveAt($i) }
    }
    $lines.Add("$Name=$Value")
}
Set-EnvValue 'EPIC_ASSET_ROOTS' 'C:\Users\demoadmin\Desktop\assets'
Set-EnvValue 'EPIC_FILE_ROOTS' 'none'
Set-EnvValue 'EPIC_SKILL_TIMEOUT_SECONDS' '420'
Set-EnvValue 'EPIC_MAX_BROWSER_STEPS' '80'
Set-EnvValue 'EPIC_DIAGNOSTICS_DIR' 'C:\EpicDemo\service\diagnostics'
[IO.File]::WriteAllLines($envPath, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))

# Restart only the API listener; keep Edge (Epic login) and the tunnel running.
foreach ($id in @(Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)) {
    Stop-Process -Id $id -Force -EA SilentlyContinue
}
Start-Sleep 2
$task = 'EpicDemoApi'
# The launcher opens the agent in Windows Terminal (run.ps1 -KeepAlive) and returns.
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument (
    "-NoProfile -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$service\agent-terminal.ps1`" -Port 8000 -KeepAlive"
) -WorkingDirectory $service
$principal = New-ScheduledTaskPrincipal -UserId 'demoadmin' -LogonType Interactive -RunLevel Limited
# Classic-console fallback: the task ends when the API exits so Task Scheduler restarts it.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
$keepAliveHost = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like '*run.ps1*-KeepAlive*' })
if (-not $keepAliveHost) { Stop-ScheduledTask -TaskName $task -EA SilentlyContinue }
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings -Force | Out-Null
# A running keep-alive host restarts the API itself with the new files.
if (-not $keepAliveHost) { Start-ScheduledTask -TaskName $task }
$deadline = [DateTime]::UtcNow.AddSeconds(90)
do { Start-Sleep 2; $h = $null; try { $h = Invoke-RestMethod 'http://127.0.0.1:8000/healthz' -TimeoutSec 2 } catch {} }
while ($h.status -ne 'ok' -and [DateTime]::UtcNow -lt $deadline)
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue | Select-Object -First 1
[pscustomobject]@{
    api = $h.status; api_pid = $listener.OwningProcess
    cdp = [bool](Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue)
    skills = (Get-ChildItem "$service\src\epic_adapter\skills" -Directory).Name -join ','
    assets = (Get-ChildItem 'C:\Users\demoadmin\Desktop\assets' -File).Name -join ','
} | ConvertTo-Json -Compress
