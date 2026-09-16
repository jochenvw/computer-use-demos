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
$previousStorageKey = $env:AZURE_STORAGE_KEY
try {
    & git -C $repoRoot archive --format zip --output $archivePath "${commit}:demos/epic-ehr"
    if ($LASTEXITCODE -ne 0) { throw 'Could not package tracked Epic demo source.' }
    $storage = & az deployment group show --subscription $SubscriptionId --resource-group $ResourceGroup `
        --name epic-desktop --query properties.outputs.artifactStorageName.value --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $storage) { throw 'The deployment has no private artifact storage account.' }
    $env:AZURE_STORAGE_KEY = & az storage account keys list --subscription $SubscriptionId `
        --resource-group $ResourceGroup --account-name $storage --query '[0].value' --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $env:AZURE_STORAGE_KEY) { throw 'Artifact upload authorization failed.' }
    & az storage blob upload --account-name $storage --container-name releases --name "$commit.zip" `
        --file $archivePath --overwrite true --content-type application/zip --auth-mode key --output none --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Private artifact upload failed.' }
    $expiry = [DateTime]::UtcNow.AddHours(1).ToString('yyyy-MM-ddTHH:mmZ')
    $sas = & az storage blob generate-sas --account-name $storage --container-name releases --name "$commit.zip" `
        --permissions r --expiry $expiry --https-only --auth-mode key --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $sas) { throw 'Could not issue the short-lived read-only artifact token.' }
    $uri = "https://$storage.blob.core.windows.net/releases/${commit}.zip?$sas"
    $parameters = @{
        ArchiveUriBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($uri))
        ArchiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
        SourceCommit = $commit
    }
    $command = "install-agent-$($commit.Substring(0, 8))-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    & (Join-Path $PSScriptRoot 'run-vm-script.ps1') -SubscriptionId $SubscriptionId `
        -ResourceGroup $ResourceGroup -CommandName $command -ProtectedParameters $parameters `
        -ScriptPath (Join-Path $PSScriptRoot 'install-agent.ps1')
} finally {
    $env:AZURE_STORAGE_KEY = $previousStorageKey
    $sas = $null
    $uri = $null
    $parameters = $null
    if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath }
}
