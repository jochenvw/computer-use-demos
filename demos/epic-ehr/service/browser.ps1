[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [uri]$EpicUrl,
    [ValidateRange(1, 65535)]
    [int]$DebugPort = 9222
)

$ErrorActionPreference = 'Stop'
if ($EpicUrl.Scheme -ne 'https' -or $EpicUrl.UserInfo) {
    throw 'EpicUrl must be an HTTPS URL with no embedded credentials.'
}
$edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $edge)) {
    throw 'Microsoft Edge is not installed in the expected location.'
}
$profile = Join-Path $env:LOCALAPPDATA 'EpicRetrievalDemo\BrowserProfile'
Write-Host 'Opening a dedicated browser profile. Log in manually with an authorized READ-ONLY account.'
Write-Host "The debugging endpoint must stay loopback-only on port $DebugPort. Never tunnel this port."
& $edge "--remote-debugging-port=$DebugPort" '--remote-debugging-address=127.0.0.1' `
    "--user-data-dir=$profile" '--no-first-run' $EpicUrl.AbsoluteUri
