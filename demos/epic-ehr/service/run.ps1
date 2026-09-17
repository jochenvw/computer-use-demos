[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$BannerOnly,
    [switch]$WithTunnel
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    # Values in the shell take precedence over local .env entries.
    $envFile = if ($env:EPIC_ENV_FILE) { $env:EPIC_ENV_FILE } else { Join-Path $PSScriptRoot '.env' }
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $name = $Matches[1]
                $value = $Matches[2].Trim().Trim('"').Trim("'")
                if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
                    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
                }
            }
        }
    }
    $flags = @('--port', "$Port")
    if ($BannerOnly) { $flags += '--banner-only' }
    if ($WithTunnel) { $flags += '--tunnel' }
    & uv run --frozen epic-agent @flags
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
