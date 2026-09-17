[CmdletBinding()]
param(
    [ValidateSet('RunInstalled', 'InstallVersion', 'ApprovedChannel')]
    [string]$Mode = 'RunInstalled',
    [string]$Version,
    [string]$Channel = 'stable',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'EpicDemo'),
    [string]$Repository = 'jochenvw/computer-use-demos',
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [ValidateRange(1, 300)][int]$DrainTimeoutSeconds = 60,
    [switch]$WithTunnel
)

$ErrorActionPreference = 'Stop'
$releasesRoot = Join-Path $InstallRoot 'releases'
$stagingRoot = Join-Path $InstallRoot 'staging'
$sharedRoot = Join-Path $InstallRoot 'shared'
$statePath = Join-Path $InstallRoot 'current.json'
$sessionPath = Join-Path $InstallRoot 'session.json'
$envFile = Join-Path $sharedRoot '.env'
$mutex = [Threading.Mutex]::new($false, 'Local\EpicRetrievalDemoLauncher')
if (-not $mutex.WaitOne(0)) { throw 'Another Epic launcher operation is already running.' }

function Read-EnvFile([string]$Path) {
    $values = @{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in Get-Content -LiteralPath $Path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $values
}

function Test-ProcessAlive([int]$Id) {
    return $null -ne (Get-Process -Id $Id -ErrorAction SilentlyContinue)
}

function Get-CurrentTag {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    return (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json).tag
}

function Stop-ActiveDemoForUpdate {
    if (-not (Test-Path -LiteralPath $sessionPath)) { return }
    $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
    if (-not (Test-ProcessAlive $session.processId)) {
        Remove-Item -LiteralPath $sessionPath
        return
    }
    $values = Read-EnvFile $envFile
    if (-not $values.API_BEARER_TOKEN) {
        throw 'The active demo cannot be drained because its API token is unavailable.'
    }
    $headers = @{ Authorization = 'Bearer ' + $values.API_BEARER_TOKEN }
    try {
        $drain = Invoke-RestMethod "http://127.0.0.1:$($session.port)/v1/admin/drain?timeout_seconds=$DrainTimeoutSeconds" `
            -Method Post -Headers $headers -TimeoutSec ($DrainTimeoutSeconds + 5)
    } catch {
        throw 'The active demo did not drain; it remains running and the update was cancelled.'
    }
    if (-not $drain.process_id) { throw 'The drained API did not report its owned process ID.' }
    Stop-Process -Id $drain.process_id
    Wait-Process -Id $drain.process_id -Timeout 15 -ErrorAction SilentlyContinue
    Wait-Process -Id $session.processId -Timeout 15 -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $sessionPath
}

function Test-Release([string]$ReleaseRoot) {
    $service = Join-Path $ReleaseRoot 'demos\epic-ehr\service'
    $fixtures = Join-Path $ReleaseRoot 'demos\epic-ehr\fixtures'
    $uv = (Get-Command uv -ErrorAction Stop).Source
    & $uv sync --project $service --python 3.13 --locked --extra test --default-index 'https://pypi.org/simple' --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Release dependency installation failed.' }
    $python = Join-Path $service '.venv\Scripts\python.exe'
    $testPort = 18000 + (Get-Random -Minimum 0 -Maximum 1000)
    $previous = @{
        API_BEARER_TOKEN = $env:API_BEARER_TOKEN
        EPIC_BACKEND = $env:EPIC_BACKEND
        EPIC_FIXTURE_ROOT = $env:EPIC_FIXTURE_ROOT
        EPIC_FILE_ROOTS = $env:EPIC_FILE_ROOTS
        EPIC_AUDIT_PATH = $env:EPIC_AUDIT_PATH
    }
    $env:API_BEARER_TOKEN = [Guid]::NewGuid().ToString('N')
    $env:EPIC_BACKEND = 'fixture'
    $env:EPIC_FIXTURE_ROOT = $fixtures
    $env:EPIC_FILE_ROOTS = Join-Path $fixtures 'files'
    $temporaryAudit = Join-Path $env:TEMP ("epic-release-audit-" + [Guid]::NewGuid().ToString('N') + '.jsonl')
    $env:EPIC_AUDIT_PATH = $temporaryAudit
    $process = Start-Process -FilePath $python -ArgumentList @(
        '-m', 'epic_adapter.console', '--port', "$testPort"
    ) -WorkingDirectory $service -PassThru -WindowStyle Hidden
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            if ($process.HasExited) { throw 'Release API exited during validation.' }
            try {
                $health = Invoke-RestMethod "http://127.0.0.1:$testPort/healthz" -TimeoutSec 2
                if ($health.status -eq 'ok') { break }
            } catch { }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($health.status -ne 'ok') { throw 'Release API health validation timed out.' }
        $headers = @{ Authorization = 'Bearer ' + $env:API_BEARER_TOKEN }
        $job = Invoke-RestMethod "http://127.0.0.1:$testPort/v1/retrieval-jobs" -Method Post `
            -Headers $headers -ContentType 'application/json' `
            -Body '{"patient_id":"DEMO-100042","source":"ehr","resources":["observations"],"observation_codes":["85354-9"]}'
        do {
            $status = Invoke-RestMethod "http://127.0.0.1:$testPort$($job.status_url)" -Headers $headers
            if ($status.status -in @('complete', 'failed')) { break }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($status.status -ne 'complete') { throw 'Synthetic release retrieval failed.' }
    } finally {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        if (Test-Path -LiteralPath $temporaryAudit) { Remove-Item -LiteralPath $temporaryAudit }
        foreach ($key in $previous.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
        }
    }
}

function Install-Release([string]$Tag) {
    if ($Tag -notmatch '^epic-v[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?$') {
        throw 'Release version must be an exact epic-v* tag.'
    }
    $destination = Join-Path $releasesRoot $Tag
    Stop-ActiveDemoForUpdate
    if (Test-Path -LiteralPath $destination) { return $destination }
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
    $staging = Join-Path $stagingRoot ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    try {
        $headers = @{ 'User-Agent' = 'Epic-Retrieval-Demo-Launcher' }
        if ($env:EPIC_RELEASE_GITHUB_TOKEN) {
            $headers.Authorization = 'Bearer ' + $env:EPIC_RELEASE_GITHUB_TOKEN
            $env:GH_TOKEN = $env:EPIC_RELEASE_GITHUB_TOKEN
        }
        $release = Invoke-RestMethod "https://api.github.com/repos/$Repository/releases/tags/$Tag" -Headers $headers
        $assetName = "epic-ehr-$Tag-windows-x64.zip"
        $asset = @($release.assets | Where-Object name -eq $assetName)
        if ($asset.Count -ne 1) { throw "Release $Tag does not contain $assetName." }
        $archive = Join-Path $staging $assetName
        $downloadHeaders = $headers.Clone()
        $downloadHeaders.Accept = 'application/octet-stream'
        Invoke-WebRequest -UseBasicParsing -Uri $asset[0].url -Headers $downloadHeaders -OutFile $archive
        $gh = (Get-Command gh -ErrorAction Stop).Source
        & $gh attestation verify $archive --repo $Repository
        if ($LASTEXITCODE -ne 0) { throw 'GitHub artifact attestation verification failed.' }
        $content = Join-Path $staging 'content'
        Expand-Archive -LiteralPath $archive -DestinationPath $content
        $manifest = Get-Content -LiteralPath (Join-Path $content 'release-manifest.json') -Raw | ConvertFrom-Json
        if ($manifest.tag -ne $Tag -or $manifest.commit -notmatch '^[a-f0-9]{40}$') {
            throw 'Release manifest does not match the selected version.'
        }
        $forbidden = Get-ChildItem -LiteralPath $content -Recurse -Force | Where-Object {
            $_.Name -in @('.env', 'audit.jsonl', 'BrowserProfile', 'screenshots', 'downloads', '.venv')
        }
        if ($forbidden) { throw 'Release contains forbidden configuration or runtime data.' }
        Test-Release $content
        Move-Item -LiteralPath $content -Destination $destination
        return $destination
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    }
}

function Start-Release([string]$Tag) {
    $releaseRoot = Join-Path $releasesRoot $Tag
    $service = Join-Path $releaseRoot 'demos\epic-ehr\service'
    if (-not (Test-Path -LiteralPath (Join-Path $service 'run.ps1'))) {
        throw "Installed release $Tag is incomplete."
    }
    if (Test-Path -LiteralPath $sessionPath) {
        $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
        if (Test-ProcessAlive $session.processId) { throw 'Epic demo is already running.' }
        Remove-Item -LiteralPath $sessionPath
    }
    $values = Read-EnvFile $envFile
    foreach ($key in $values.Keys) {
        [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process')
    }
    $env:EPIC_ENV_FILE = $envFile
    if (-not $env:EPIC_FIXTURE_ROOT) {
        $env:EPIC_FIXTURE_ROOT = Join-Path $releaseRoot 'demos\epic-ehr\fixtures'
    }
    if (-not $env:EPIC_FILE_ROOTS) {
        $env:EPIC_FILE_ROOTS = Join-Path $env:EPIC_FIXTURE_ROOT 'files'
    }
    if ($env:EPIC_BACKEND -in @('copilot', 'computer-use')) {
        if (-not $env:EPIC_READY_URL_PREFIX) {
            throw 'Set EPIC_READY_URL_PREFIX before launching live browser mode.'
        }
        Start-Process powershell.exe -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'RemoteSigned', '-File',
            (Join-Path $service 'browser.ps1'), '-EpicUrl', $env:EPIC_READY_URL_PREFIX
        ) -WorkingDirectory $service | Out-Null
    }
    $arguments = @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'RemoteSigned', '-File',
        (Join-Path $service 'run.ps1'), '-Port', "$Port"
    )
    if ($WithTunnel) { $arguments += '-WithTunnel' }
    $process = Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $service -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if ($process.HasExited) { throw "Epic release $Tag exited before health readiness." }
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/healthz" -TimeoutSec 2
            if ($health.status -eq 'ok') { break }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($health.status -ne 'ok') {
        Stop-Process -Id $process.Id -Force
        throw "Epic release $Tag failed its activation health check."
    }
    [ordered]@{
        processId = $process.Id
        tag = $Tag
        port = $Port
        startedAt = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $sessionPath -Encoding UTF8
    return $process
}

try {
    foreach ($path in @($releasesRoot, $stagingRoot, $sharedRoot)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $envFile)) {
        throw 'Run Bootstrap-EpicDemo.ps1 before using the launcher.'
    }
    $previousTag = Get-CurrentTag
    if ($Mode -eq 'ApprovedChannel') {
        $channels = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'channels.json') -Raw | ConvertFrom-Json
        $Version = $channels.$Channel
        if (-not $Version) { throw "Approved channel '$Channel' does not identify an exact release tag." }
    } elseif ($Mode -eq 'RunInstalled') {
        $Version = $previousTag
        if (-not $Version) { throw 'No installed release is active. Select an exact version first.' }
    } elseif (-not $Version) {
        throw 'InstallVersion requires -Version with an exact epic-v* tag.'
    }

    $releaseRoot = if ($Mode -eq 'RunInstalled') {
        Join-Path $releasesRoot $Version
    } else {
        Install-Release $Version
    }
    if (-not (Test-Path -LiteralPath $releaseRoot)) { throw "Release $Version is not installed." }
    try {
        Start-Release $Version | Out-Null
        [ordered]@{
            tag = $Version
            previousTag = if ($previousTag -ne $Version) { $previousTag } else { $null }
            activatedAt = [DateTime]::UtcNow.ToString('o')
        } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
        Write-Output "Epic Retrieval Agent $Version is healthy on http://127.0.0.1:$Port."
    } catch {
        if ($previousTag -and $previousTag -ne $Version -and
                (Test-Path -LiteralPath (Join-Path $releasesRoot $previousTag))) {
            Start-Release $previousTag | Out-Null
            Write-Warning "Activation failed; restored $previousTag."
        }
        throw
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
