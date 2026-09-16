[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{32}$')][string]$TransferId,
    [Parameter(Mandatory)][ValidateRange(1, 1024)][int]$PartCount,
    [Parameter(Mandatory)][string]$ArchiveSha256,
    [Parameter(Mandatory)][string]$SourceCommit,
    [string]$AdminUser = 'demoadmin'
)

$ErrorActionPreference = 'Stop'
$root = 'C:\EpicDemo'
$service = Join-Path $root 'service'
$uv = 'C:\DemoTools\uv\uv.exe'
if (-not (Test-Path -LiteralPath $uv)) { throw 'Run bootstrap-tools.ps1 first.' }
if ($SourceCommit -notmatch '^[a-f0-9]{40}$') { throw 'A full source commit ID is required.' }
New-Item -ItemType Directory -Path $root -Force | Out-Null
$staging = Join-Path "$root\.staging" $TransferId
$parts = @(0..($PartCount - 1) | ForEach-Object { Join-Path $staging ('{0:D4}.part' -f $_) })
$deadline = [DateTime]::UtcNow.AddMinutes(5)
do {
    $missing = @($parts | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing.Count -eq 0) { break }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)
if ($missing.Count) { throw 'Source transfer did not complete. Inspect the managed source-part commands.' }
$archive = Join-Path $root 'source-install.zip'
try {
    $stream = [IO.File]::Create($archive)
    try {
        foreach ($part in $parts) {
            $bytes = [IO.File]::ReadAllBytes($part)
            $stream.Write($bytes, 0, $bytes.Length)
        }
    } finally {
        $stream.Dispose()
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $ArchiveSha256) {
        throw 'Source archive integrity check failed.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    foreach ($part in $parts) { if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part } }
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging }
}
$env:UV_PYTHON_INSTALL_DIR = 'C:\DemoTools\python'
$env:Path = 'C:\DemoTools\uv;C:\DemoTools\devtunnel;' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
& $uv sync --project $service --python 3.13 --extra test --default-index 'https://pypi.org/simple' --quiet
if ($LASTEXITCODE -ne 0) { throw 'Agent dependency installation failed.' }
$python = Join-Path $service '.venv\Scripts\python.exe'
$sdkVersion = & $python -c "from importlib.metadata import version; print(version('github-copilot-sdk'))"
if ($LASTEXITCODE -ne 0) { throw 'The pinned Copilot SDK was not installed.' }
$runtimeRoot = "C:\DemoTools\copilot-runtime\sdk-$sdkVersion"
$env:COPILOT_CLI_EXTRACT_DIR = $runtimeRoot
& $python -m copilot download-runtime
if ($LASTEXITCODE -ne 0) { throw 'SDK-matched runtime provisioning failed.' }

$envFile = Join-Path $service '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    $secretBytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($secretBytes) } finally { $rng.Dispose() }
    $apiToken = [Convert]::ToBase64String($secretBytes)
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($identity in @(
        (Get-LocalUser -Name $AdminUser).SID,
        [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    )) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow'))
    }
    New-Item -ItemType File -Path $envFile | Out-Null
    Set-Acl -LiteralPath $envFile -AclObject $acl
    @"
API_BEARER_TOKEN=$apiToken
EPIC_BACKEND=fixture
EPIC_FIXTURE_ROOT=..\fixtures
EPIC_FILE_ROOTS=..\fixtures\files
MODEL_DEPLOYMENT=gpt-6-astra
COPILOT_CLI_EXTRACT_DIR=$runtimeRoot
EPIC_CACHE_TTL_SECONDS=900
EPIC_CACHE_MAX_ENTRIES=16
EPIC_CACHE_MAX_BYTES=8388608
# Enable live mode only after manual Epic browser and model authentication:
# EPIC_BACKEND=copilot
# EPIC_COMPUTER_USE_ENABLED=1
# EPIC_ORIGIN=https://your-authorized-epic-host
# COPILOT_GITHUB_TOKEN=
"@ | Set-Content -LiteralPath $envFile -Encoding UTF8
    $apiToken = $null
}

$shell = New-Object -ComObject WScript.Shell
foreach ($shortcut in @(
    @{ Name = 'Epic Agent with Tunnel'; Script = 'run.ps1'; Extra = ' -WithTunnel' },
    @{ Name = 'Epic Agent Local Only'; Script = 'run.ps1'; Extra = '' },
    @{ Name = 'Epic API Tester'; Script = 'testing.ps1'; Extra = '' }
)) {
    $link = $shell.CreateShortcut("$env:PUBLIC\Desktop\$($shortcut.Name).lnk")
    $link.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $link.Arguments = "-NoProfile -NoExit -ExecutionPolicy RemoteSigned -File `"$service\$($shortcut.Script)`"$($shortcut.Extra)"
    $link.WorkingDirectory = $service
    $link.Save()
}
$link = $shell.CreateShortcut("$env:PUBLIC\Desktop\Configure Epic Agent.lnk")
$link.TargetPath = "$env:SystemRoot\System32\notepad.exe"
$link.Arguments = "`"$envFile`""
$link.Save()
@'
USE EpicDemo;
SELECT p.PatientId, p.DisplayName, o.LoincCode, o.Description, o.NumericValue, o.Unit, o.RecordedAt
FROM dbo.Patients AS p
JOIN dbo.Observations AS o ON o.PatientId = p.PatientId
ORDER BY o.ObservationId;
'@ | Set-Content -LiteralPath "$env:PUBLIC\Desktop\Synthetic SQL Demo.sql" -Encoding UTF8
@'
EPIC / SQL DEMO - SYNTHETIC DATA ONLY

1. Run "Epic Agent Local Only" to try the offline fixture API.
2. For remote testing, open a normal PowerShell terminal and run:
       devtunnel user login
   Then run "Epic Agent with Tunnel". Copy the actual HTTPS URL it prints.
3. "Configure Epic Agent" opens the private local .env. Copy API_BEARER_TOKEN
   into the local tester's masked token field. Never publish or log this value.
   The tester also needs a devtunnel connect token when tunnel authentication requires it.
4. To activate browser computer use, configure EPIC_BACKEND=copilot, explicit
   opt-in, exact Epic HTTPS origin, and Copilot token (or approved Azure BYOM).
   Run service\browser.ps1, log in to Epic manually with a read-only account.
   Restart the agent and use Bypass cache to force fresh work.
5. SSMS: connect to localhost with Windows authentication. The database EpicDemo
   contains synthetic BP rows. Open "Synthetic SQL Demo.sql".
   SSMS desktop computer use is NOT wired into the API yet.

Keep the RDP desktop session open for interactive demonstration.
Do not publish RDP3389, SQL1433 or browser CDP9222 through devtunnel.
SQL Server Developer is for development/testing, not production workloads.
'@ | Set-Content -LiteralPath "$env:PUBLIC\Desktop\READ ME FIRST.txt" -Encoding UTF8

$env:EPIC_BACKEND = 'fixture'
$env:API_BEARER_TOKEN = (
    Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^API_BEARER_TOKEN=' } | Select-Object -First 1
).Substring('API_BEARER_TOKEN='.Length)
$env:EPIC_FIXTURE_ROOT = Join-Path $root 'fixtures'
$env:EPIC_FILE_ROOTS = Join-Path $root 'fixtures\files'
$process = Start-Process -FilePath $python -ArgumentList @('-m', 'epic_adapter.console', '--port', '18000') `
    -WorkingDirectory $service -PassThru -WindowStyle Hidden
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if ($process.HasExited) { throw 'The installed API exited before readiness.' }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:18000/healthz' -TimeoutSec 2
            if ($health.status -eq 'ok') { break }
        } catch [System.Net.WebException] {
            if ([DateTime]::UtcNow -ge $deadline) { throw }
        }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($health.status -ne 'ok') { throw 'Installed API health check timed out.' }
    $headers = @{ Authorization = 'Bearer ' + $env:API_BEARER_TOKEN }
    $job = Invoke-RestMethod 'http://127.0.0.1:18000/v1/retrieval-jobs' -Method Post -Headers $headers `
        -ContentType 'application/json' -Body '{"patient_id":"DEMO-100042","source":"ehr","resources":["observations"],"observation_codes":["85354-9"]}'
    do {
        $status = Invoke-RestMethod "http://127.0.0.1:18000$($job.status_url)" -Headers $headers
        if ($status.status -in @('complete', 'failed')) { break }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($status.status -ne 'complete') { throw 'Installed API synthetic retrieval did not complete.' }
    $bundle = Invoke-RestMethod "http://127.0.0.1:18000$($job.result_url)" -Headers $headers
    if ($bundle.resourceType -ne 'Bundle' -or $bundle.entry[0].resource.component[0].valueQuantity.value -ne 120) {
        throw 'Installed API did not return the expected synthetic FHIR blood pressure.'
    }
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    $env:API_BEARER_TOKEN = $null
}
@{ sourceCommit = $SourceCommit; apiReady = $true; backend = 'fixture'; installedAt = [DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'install-status.json') -Encoding UTF8
Write-Output 'Agent installed and synthetic FHIR retrieval verified. Use the desktop shortcuts after RDP login.'
