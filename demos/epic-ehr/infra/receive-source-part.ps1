[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{32}$')][string]$TransferId,
    [Parameter(Mandatory)][ValidateRange(0, 1023)][int]$PartIndex,
    [Parameter(Mandatory)][string]$PartBase64
)

$ErrorActionPreference = 'Stop'
if ($PartBase64.Length -gt 16384) { throw 'Source part exceeds the protected-parameter transport limit.' }
$bytes = [Convert]::FromBase64String($PartBase64)
if ($bytes.Length -eq 0 -or $bytes.Length -gt 12288) { throw 'Invalid source part size.' }
$staging = Join-Path 'C:\EpicDemo\.staging' $TransferId
New-Item -ItemType Directory -Path $staging -Force | Out-Null
$part = Join-Path $staging ('{0:D4}.part' -f $PartIndex)
$temporary = "$part.tmp"
try {
    [IO.File]::WriteAllBytes($temporary, $bytes)
    Move-Item -LiteralPath $temporary -Destination $part -Force
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}
Write-Output "Source part $PartIndex received."
