[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [switch]$ManualCredentials,
    [switch]$NoOpen,
    [switch]$Stage
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stateRoot = Join-Path $repoRoot ".azure\$ResourceGroup"
$environmentNames = @(
    'EPIC_TESTER_TUNNEL_URL',
    'EPIC_TESTER_API_BEARER_TOKEN',
    'EPIC_TESTER_TUNNEL_TOKEN'
)
$previousValues = @{}

function ConvertFrom-ProtectedString {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

Push-Location $PSScriptRoot
try {
    foreach ($name in $environmentNames) {
        $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    if (-not $ManualCredentials) {
        $originPath = Join-Path $stateRoot 'vm-tunnel-origin.txt'
        $apiTokenPath = Join-Path $stateRoot 'vm-api-token.xml'
        $tunnelTokenPath = Join-Path $stateRoot 'vm-tunnel-connect-token.xml'
        $credentialPaths = @($originPath, $apiTokenPath, $tunnelTokenPath)
        $existingPaths = @($credentialPaths | Where-Object { Test-Path -LiteralPath $_ })
        if ($existingPaths.Count -notin @(0, $credentialPaths.Count)) {
            throw "Protected demo connection is incomplete under $stateRoot."
        }
        if ($existingPaths.Count -eq $credentialPaths.Count) {
            $origin = (Get-Content -LiteralPath $originPath -Raw).Trim()
            $apiToken = ConvertFrom-ProtectedString (Import-Clixml -LiteralPath $apiTokenPath)
            $tunnelToken = ConvertFrom-ProtectedString (Import-Clixml -LiteralPath $tunnelTokenPath)
            [Environment]::SetEnvironmentVariable('EPIC_TESTER_TUNNEL_URL', $origin, 'Process')
            [Environment]::SetEnvironmentVariable('EPIC_TESTER_API_BEARER_TOKEN', $apiToken, 'Process')
            [Environment]::SetEnvironmentVariable('EPIC_TESTER_TUNNEL_TOKEN', $tunnelToken, 'Process')
            Write-Host 'Using the protected local demo connection; no credential paste is required.'
        }
    }
    $arguments = @('run', '--frozen', 'epic-tester', '--port', "$Port")
    if (-not $NoOpen) { $arguments += '--open' }
    if ($Stage) { $arguments += '--stage' }
    & uv @arguments
    exit $LASTEXITCODE
} finally {
    $apiToken = $null
    $tunnelToken = $null
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousValues[$name], 'Process')
    }
    Pop-Location
}
