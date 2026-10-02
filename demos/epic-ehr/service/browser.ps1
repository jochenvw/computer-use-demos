[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [uri]$EpicUrl,
    [ValidateRange(1, 65535)]
    [int]$DebugPort = 9222,
    [switch]$AllowLoopbackTraining,
    # Fallback: open a normal tabbed window instead of the minimal app window.
    [switch]$Tabbed
)

$ErrorActionPreference = 'Stop'
$loopbackTraining = (
    $AllowLoopbackTraining -and
    $EpicUrl.Scheme -eq 'http' -and
    $EpicUrl.Host -in @('127.0.0.1', 'localhost') -and
    $EpicUrl.Port -gt 0
)
if (($EpicUrl.Scheme -ne 'https' -and -not $loopbackTraining) -or $EpicUrl.UserInfo) {
    throw 'EpicUrl must be HTTPS, or explicit loopback HTTP for synthetic training.'
}
$edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path -LiteralPath $edge)) {
    throw 'Microsoft Edge is not installed in the expected location.'
}
$profile = Join-Path $env:LOCALAPPDATA 'EpicRetrievalDemo\BrowserProfile'
# Exactly one EMR page is allowed: reuse an already open window instead of adding a second.
try {
    $open = @(Invoke-RestMethod "http://127.0.0.1:$DebugPort/json/list" -TimeoutSec 2 |
        Where-Object { $_.type -eq 'page' -and $_.url.StartsWith($EpicUrl.GetLeftPart('Authority')) })
} catch { $open = @() }
if ($open.Count) {
    Write-Host 'The dedicated EMR window is already open; not opening another one.'
    return
}
Write-Host 'Opening a dedicated browser profile. Log in manually with an authorized READ-ONLY account.'
Write-Host "The debugging endpoint must stay loopback-only on port $DebugPort. Never tunnel this port."
# App mode: one minimal window (no tabs, address bar or toolbar); CDP still sees it as a page.
$target = if ($Tabbed) { $EpicUrl.AbsoluteUri } else { "--app=$($EpicUrl.AbsoluteUri)" }
& $edge "--remote-debugging-port=$DebugPort" '--remote-debugging-address=127.0.0.1' `
    "--user-data-dir=$profile" '--no-first-run' '--start-maximized' $target
