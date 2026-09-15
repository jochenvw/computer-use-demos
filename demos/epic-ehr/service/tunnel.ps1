[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command devtunnel -ErrorAction SilentlyContinue)) {
    throw 'Install the Microsoft dev tunnels CLI, then run devtunnel user login.'
}
$health = Invoke-RestMethod "http://127.0.0.1:$Port/healthz"
if ($health.status -ne 'ok') {
    throw 'Start run.ps1 before opening a tunnel.'
}
Write-Host 'Opening an authenticated, one-hour dev tunnel. No inbound VM firewall rule is needed.'
Write-Host 'The caller needs both tunnel access and the API bearer token. Ctrl+C closes the tunnel.'
& devtunnel host --port-numbers $Port --protocol http --expiration 1h
if ($LASTEXITCODE -ne 0) {
    throw 'Dev tunnel failed. Check devtunnel user login and network egress.'
}
