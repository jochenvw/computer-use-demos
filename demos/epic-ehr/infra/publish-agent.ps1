[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$SourceRef = 'HEAD'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stateRoot = Join-Path $repoRoot ".azure\$ResourceGroup"
if (-not (Test-Path -LiteralPath $stateRoot)) { throw 'Deploy the VM first.' }
$commit = & git -C $repoRoot rev-parse "${SourceRef}^{commit}"
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') { throw 'SourceRef must resolve to a Git commit.' }
$archivePath = Join-Path $stateRoot 'epic-demo-source.zip'
$transferId = [guid]::NewGuid().ToString('N')
$started = @()
try {
    & git -C $repoRoot archive --format zip --output $archivePath "${commit}:demos/epic-ehr"
    if ($LASTEXITCODE -ne 0) { throw 'Could not package tracked Epic demo source.' }
    $bytes = [IO.File]::ReadAllBytes($archivePath)
    $partCount = [int][Math]::Ceiling($bytes.Length / 12288)
    if ($partCount -lt 1 -or $partCount -gt 1024) { throw 'Source archive must be between 1 byte and 12 MiB.' }
    for ($index = 0; $index -lt $partCount; $index++) {
        $offset = $index * 12288
        $count = [Math]::Min(12288, $bytes.Length - $offset)
        $parameters = @{
            TransferId = $transferId
            PartIndex = "$index"
            PartBase64 = [Convert]::ToBase64String($bytes, $offset, $count)
        }
        $command = "source-$($transferId.Substring(0, 8))-$index"
        & (Join-Path $PSScriptRoot 'run-vm-script.ps1') -SubscriptionId $SubscriptionId `
            -ResourceGroup $ResourceGroup -CommandName $command -ProtectedParameters $parameters `
            -ScriptPath (Join-Path $PSScriptRoot 'receive-source-part.ps1') -StartOnly
        $started += $command
    }
    $parameters = @{
        TransferId = $transferId
        PartCount = "$partCount"
        ArchiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
        SourceCommit = $commit
    }
    $command = "install-agent-$($commit.Substring(0, 8))-$($transferId.Substring(0, 8))"
    & (Join-Path $PSScriptRoot 'run-vm-script.ps1') -SubscriptionId $SubscriptionId `
        -ResourceGroup $ResourceGroup -CommandName $command -ProtectedParameters $parameters `
        -ScriptPath (Join-Path $PSScriptRoot 'install-agent.ps1')
} finally {
    $parameters = $null
    foreach ($command in $started) {
        & az vm run-command delete --subscription $SubscriptionId --resource-group $ResourceGroup `
            --vm-name epicdemo-desktop-vm --run-command-name $command --yes --only-show-errors --output none
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove transient source command $command." }
    }
    if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath }
}
