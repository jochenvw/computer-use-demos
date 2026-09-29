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
try {
    & git -C $repoRoot archive --format zip --output $archivePath "${commit}:demos/epic-ehr"
    if ($LASTEXITCODE -ne 0) { throw 'Could not package tracked Epic demo source.' }
    $bytes = [IO.File]::ReadAllBytes($archivePath)
    $partSize = 4096
    $partCount = [int][Math]::Ceiling($bytes.Length / $partSize)
    if ($partCount -lt 1 -or $partCount -gt 1024) { throw 'Source archive must be between 1 byte and 12 MiB.' }
    for ($index = 0; $index -lt $partCount; $index++) {
        $offset = $index * $partSize
        $count = [Math]::Min($partSize, $bytes.Length - $offset)
        $partBase64 = [Convert]::ToBase64String($bytes, $offset, $count)
        & az vm run-command invoke --subscription $SubscriptionId `
            --resource-group $ResourceGroup --name epicdemo-desktop-vm `
            --command-id RunPowerShellScript `
            --scripts "@$(Join-Path $PSScriptRoot 'receive-source-part.ps1')" `
            --parameters "TransferId=$transferId" "PartIndex=$index" `
            "PartBase64=$partBase64" --only-show-errors --output none
        if ($LASTEXITCODE -ne 0) { throw "Source upload part $index failed." }
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
    $partBase64 = $null
    if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath }
}
