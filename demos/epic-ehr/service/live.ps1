[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Configure Epic Agent before starting the live demo.'
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$required = @(
    'API_BEARER_TOKEN',
    'EPIC_BACKEND',
    'EPIC_COMPUTER_USE_ENABLED',
    'EPIC_ORIGIN',
    'EPIC_READY_URL_PREFIX',
    'EPIC_BROWSER_CDP_URL',
    'MODEL_DEPLOYMENT'
)
$missing = @($required | Where-Object {
    -not $values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($values[$_])
})
if ($missing.Count) {
    throw 'Complete the Epic configuration first: ' + ($missing -join ', ')
}
if ($values.EPIC_BACKEND -notin @('copilot', 'computer-use')) {
    throw 'EPIC_BACKEND must be copilot for the live demo.'
}
if ($values.EPIC_COMPUTER_USE_ENABLED -ne '1') {
    throw 'EPIC_COMPUTER_USE_ENABLED must be 1 for the live demo.'
}
if ([string]::IsNullOrWhiteSpace($values.COPILOT_GITHUB_TOKEN) -and
    [string]::IsNullOrWhiteSpace($values.AZURE_AI_FOUNDRY_ENDPOINT)) {
    throw 'Configure COPILOT_GITHUB_TOKEN or AZURE_AI_FOUNDRY_ENDPOINT first.'
}

foreach ($item in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($item.Key, $item.Value, 'Process')
}
$env:EPIC_ENV_FILE = $envFile
$portal = $null
if ($values.EPIC_SYNTHETIC_PORTAL -eq '1') {
   $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
   $portal = Start-Process -FilePath $python -ArgumentList @(
       '-m', 'epic_adapter.synthetic_portal', '--port', '8001'
   ) -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden
   $deadline = [DateTime]::UtcNow.AddSeconds(30)
   do {
       if ($portal.HasExited) {
           throw 'The synthetic Epic portal exited before readiness.'
       }
       try {
           $portalHealth = Invoke-RestMethod 'http://127.0.0.1:8001/healthz' `
               -TimeoutSec 2
       } catch {
           $portalHealth = $null
       }
       if ($portalHealth.status -ne 'ok') { Start-Sleep -Milliseconds 500 }
   } while ($portalHealth.status -ne 'ok' -and [DateTime]::UtcNow -lt $deadline)
   if ($portalHealth.status -ne 'ok') {
       throw 'The synthetic Epic portal did not become healthy.'
   }
}
$browserArguments = @(
   '-NoProfile',
   '-ExecutionPolicy', 'RemoteSigned',
   '-File', (Join-Path $PSScriptRoot 'browser.ps1'),
   '-EpicUrl', $values.EPIC_READY_URL_PREFIX
)
if ($values.EPIC_SYNTHETIC_PORTAL -eq '1') {
   $browserArguments += '-AllowLoopbackTraining'
}
Start-Process powershell.exe -ArgumentList $browserArguments `
   -WorkingDirectory $PSScriptRoot | Out-Null

Write-Host 'Dedicated Epic browser opened. Log in manually and keep exactly one Epic tab open.'
Write-Host 'The stable authenticated demo tunnel starts separately and forwards this local API.'
try {
   & (Join-Path $PSScriptRoot 'run.ps1') -Port $Port
   exit $LASTEXITCODE
} finally {
   if ($portal -and -not $portal.HasExited) {
       Stop-Process -Id $portal.Id -Force
   }
}
