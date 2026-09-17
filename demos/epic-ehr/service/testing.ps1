[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & uv run --frozen epic-tester --port $Port
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
