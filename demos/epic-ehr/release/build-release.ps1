[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^epic-v[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?$')]
    [string]$Tag,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$trackedChanges = @(& git -C $repositoryRoot status --porcelain --untracked-files=no)
if ($LASTEXITCODE -ne 0 -or $trackedChanges.Count) {
    throw 'Commit tracked changes before building a reproducible release.'
}
$commit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') {
    throw 'A full Git commit is required to build a release.'
}
$tagCommit = (& git -C $repositoryRoot rev-list -n 1 $Tag).Trim()
if ($LASTEXITCODE -ne 0 -or $tagCommit -ne $commit) {
    throw "Tag $Tag must identify the checked-out commit."
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("epic-release-" + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $work 'payload'
New-Item -ItemType Directory -Path $payload -Force | Out-Null
try {
    $tracked = @(& git -C $repositoryRoot ls-files -- 'demos/epic-ehr/service' 'demos/epic-ehr/fixtures')
    if ($LASTEXITCODE -ne 0 -or -not $tracked.Count) { throw 'No tracked release files were found.' }
    foreach ($relative in $tracked) {
        if ($relative -match '(^|/)(\.env|audit\.jsonl|BrowserProfile|screenshots|downloads|\.venv)(/|$)') {
            throw "Forbidden runtime file is tracked in the release set: $relative"
        }
        $source = Join-Path $repositoryRoot ($relative -replace '/', '\')
        $target = Join-Path $payload ($relative -replace '/', '\')
        New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target
    }
    $lockPath = Join-Path $repositoryRoot 'demos\epic-ehr\service\uv.lock'
    [ordered]@{
        schemaVersion = 1
        tag = $Tag
        commit = $commit
        dependencyLock = 'demos/epic-ehr/service/uv.lock'
        dependencyLockSha256 = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $payload 'release-manifest.json') -Encoding UTF8

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $archive = Join-Path (Resolve-Path $OutputDirectory).Path "epic-ehr-$Tag-windows-x64.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    Compress-Archive -Path (Join-Path $payload '*') -DestinationPath $archive -CompressionLevel Optimal
    Write-Output $archive
} finally {
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}
