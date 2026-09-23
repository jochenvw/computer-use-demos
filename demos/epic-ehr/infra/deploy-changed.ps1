[CmdletBinding()]
param(
    # Paths relative to demos\epic-ehr\service; defaults to git-changed service source.
    [string[]]$Files,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$VmName = 'epicdemo-desktop-vm',
    [string]$Subscription = 'e3825c9a-4bce-43e1-899e-1610156c9383'
)
$ErrorActionPreference = 'Stop'
$service = Join-Path $PSScriptRoot '..\service' | Resolve-Path
if (-not $Files) {
    Push-Location $service
    try {
        $Files = @(git ls-files -m -o --exclude-standard -- src |
            Where-Object { $_ -notmatch '__pycache__' -and (Test-Path $_) })
    } finally { Pop-Location }
}
if (-not $Files) { throw 'No changed files to deploy.' }

$work = Join-Path ([IO.Path]::GetTempPath()) ("epic-deploy-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $work | Out-Null
try {
    foreach ($file in $Files) {
        $target = Join-Path $work $file
        New-Item -ItemType Directory (Split-Path $target) -Force | Out-Null
        Copy-Item (Join-Path $service $file) $target
    }
    $zip = Join-Path ([IO.Path]::GetTempPath()) "epic-deploy-$([guid]::NewGuid().ToString('N')).zip"
    Compress-Archive -Path (Join-Path $work '*') -DestinationPath $zip -CompressionLevel Optimal
    $bytes = [IO.File]::ReadAllBytes($zip)
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash
    Remove-Item $zip
    $transfer = [guid]::NewGuid().ToString('N')
    $size = 4096
    $count = [Math]::Ceiling($bytes.Length / $size)
    Write-Host "Deploying $($Files.Count) file(s), $($bytes.Length) bytes in $count part(s)"
    $az = @('--subscription', $Subscription, '-g', $ResourceGroup, '-n', $VmName,
        '--command-id', 'RunPowerShellScript', '--query', 'value[0].message', '-o', 'tsv')
    for ($i = 0; $i -lt $count; $i++) {
        $chunk = $bytes[($i * $size)..([Math]::Min(($i + 1) * $size, $bytes.Length) - 1)]
        $b64 = [Convert]::ToBase64String([byte[]]$chunk)
        az vm run-command invoke @az --scripts "@$PSScriptRoot\receive-source-part.ps1" `
            --parameters "TransferId=$transfer" "PartIndex=$i" "PartBase64=$b64" | Write-Host
        if ($LASTEXITCODE -ne 0) { throw "Upload of part $i failed." }
    }
    az vm run-command invoke @az --scripts "@$PSScriptRoot\apply-changed-files.ps1" `
        --parameters "TransferId=$transfer" "PartCount=$count" "ArchiveSha256=$sha"
    if ($LASTEXITCODE -ne 0) { throw 'Apply failed.' }
} finally {
    Remove-Item $work -Recurse -Force -EA SilentlyContinue
}
