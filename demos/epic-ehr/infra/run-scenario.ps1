[CmdletBinding()]
param(
    [ValidateSet('emr', 'pacs', 'sql', 'files')][string]$Scenario = 'emr',
    [ValidateSet('fhir', 'omop', 'json')][string]$Format = 'fhir',
    [string]$Schema = '',
    [int]$TimeoutSeconds = 420,
    [string]$ResourceGroup = 'rg-epic-demo-swc'
)
# Operator inner loop: submit a scenario over the private tunnel, poll, print result or trace.
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..\..')
$state = Join-Path $repoRoot ".azure\$ResourceGroup"
function Read-Secret([string]$Path) {
    $secure = Import-Clixml -LiteralPath $Path
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
$origin = (Get-Content (Join-Path $state 'vm-tunnel-origin.txt') -Raw).Trim().TrimEnd('/')
$headers = @{
    Authorization = 'Bearer ' + (Read-Secret (Join-Path $state 'vm-api-token.xml'))
    'X-Tunnel-Authorization' = 'tunnel ' + (Read-Secret (Join-Path $state 'vm-tunnel-connect-token.xml'))
}
$request = @{
    emr = @{ source = 'ehr'; resources = @('patient', 'encounters', 'observations', 'documents') }
    pacs = @{ source = 'pacs'; resources = @('imaging') }
    sql = @{ source = 'sql'; resources = @('patient', 'encounters', 'observations', 'documents', 'imaging') }
    files = @{ source = 'files'; resources = @('ecg', 'observations') }
}[$Scenario]
# Same visible task for every scenario; the agent discovers where the data lives.
$request.patient_id = 'TUS-2026-0417'
$request.instruction = 'Retrieve all relevant medical information for patient Anna Ricci.'
$request.bypass_cache = $true
$job = Invoke-RestMethod "$origin/v1/retrieval-jobs" -Method Post -Headers $headers `
    -ContentType 'application/json' -Body ($request | ConvertTo-Json)
Write-Host "job $($job.job_id) submitted ($Scenario)"
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep 3
    $status = Invoke-RestMethod "$origin/v1/retrieval-jobs/$($job.job_id)" -Headers $headers
    Write-Host -NoNewline '.'
} while ($status.status -in @('queued', 'running') -and [DateTime]::UtcNow -lt $deadline)
Write-Host " $($status.status)"
Write-Host '--- timeline (what the console / test UI shows)'
foreach ($item in @($status.timeline)) {
    if ($item) { Write-Host ('{0,5}s [{1}] {2}' -f $item.t, $item.kind.ToUpper(), $item.text) }
}
if ($status.status -eq 'complete') {
    $result = Invoke-WebRequest "$origin/v1/retrieval-jobs/$($job.job_id)/result?format=$Format" `
        -Headers $headers -UseBasicParsing
    $body = if ($result.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($result.Content) } else { $result.Content }
    Write-Host '--- result'
    Write-Host ($body | ConvertFrom-Json | ConvertTo-Json -Depth 20)
    if ($Schema) {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $mapped = Invoke-RestMethod "$origin/v1/retrieval-jobs/$($job.job_id)/transform" -Method Post `
            -Headers $headers -ContentType 'application/json' -Body (@{ schema = $Schema } | ConvertTo-Json) -TimeoutSec 150
        Write-Host "--- custom schema ($([int]$sw.Elapsed.TotalSeconds)s)"
        Write-Host ($mapped | ConvertTo-Json -Depth 20)
    }
} elseif ($status.error) {
    Write-Host "error: $($status.error)"
}
$trace = Invoke-RestMethod "$origin/v1/admin/diagnostics" -Headers $headers
$shots = Join-Path $state 'diagnostics'
foreach ($run in $trace.runs) {
    Write-Host "--- trace $($run.run) ($($run.screenshots.Count) screenshot(s))"
    foreach ($e in $run.events) {
        if ($e.event -eq 'model' -and $e.source_type -in @('SkillInvokedData', 'SystemMessageData')) { continue }
        $line = $e | ConvertTo-Json -Compress -Depth 6
        if ($line.Length -gt 600) { $line = $line.Substring(0, 600) + '...' }
        Write-Host $line
    }
    $folder = Join-Path $shots $run.run
    New-Item -ItemType Directory $folder -Force | Out-Null
    foreach ($name in $run.screenshots) {
        Invoke-WebRequest "$origin/v1/admin/diagnostics/$($run.run)/$name" -Headers $headers `
            -OutFile (Join-Path $folder $name) -UseBasicParsing
    }
    Write-Host "screenshots: $folder"
}
if ($status.status -ne 'complete') { exit 1 }
