<#
.SYNOPSIS
    Launches the SRE Agent in A2A (Agent-to-Agent) server mode.
.DESCRIPTION
    Activates the virtual environment, loads configuration from .env if needed,
    and starts the A2A JSON-RPC server via uv.
.PARAMETER Port
    TCP port to listen on (default: 10100).
.PARAMETER Host
    Bind address (default: 127.0.0.1). Remote exposure requires explicit opt-in.
#>
[CmdletBinding()]
param(
    [int]$Port = 10100,
    [string]$Host = "127.0.0.1"
)

# --- Colored output helpers ---
function Write-Status  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }
function Write-Err     { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }

# --- Ctrl+C handler ---
$null = [Console]::TreatControlCAsInput
try {
    [Console]::TreatControlCAsInput = $false
} catch {
    # Non-interactive -- ignore
}

trap {
    Write-Warn "Interrupted -- shutting down gracefully."
    exit 130
}

# --- Resolve paths relative to this script ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $ScriptDir

try {
    # --- 1. Virtual-environment check ---
    if (-not (Test-Path ".venv")) {
        Write-Err "Virtual environment not found (.venv)."
        Write-Err "Run setup.ps1 first:  .\setup.ps1"
        exit 1
    }
    Write-Ok "Virtual environment found."

    # --- 2. Load .env file (always, to pick up all config) ---
    if (Test-Path ".env") {
        Write-Status "Loading configuration from .env ..."
        Get-Content ".env" | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $eqIdx = $line.IndexOf("=")
                if ($eqIdx -gt 0) {
                    $key   = $line.Substring(0, $eqIdx).Trim()
                    $value = $line.Substring($eqIdx + 1).Trim()
                    # Strip surrounding quotes
                    if ($value.Length -ge 2 -and
                        (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                         ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                        $value = $value.Substring(1, $value.Length - 2)
                    }
                    Set-Item "env:$key" $value
                }
            }
        }
    }

    # --- 3. Ensure AZURE_AI_FOUNDRY_ENDPOINT is set ---
    if (-not $env:AZURE_AI_FOUNDRY_ENDPOINT) {
        Write-Warn "AZURE_AI_FOUNDRY_ENDPOINT is not set and no .env file was found."
        $endpoint = Read-Host "Enter your Azure AI Foundry endpoint URL"
        if (-not $endpoint) {
            Write-Err "No endpoint provided -- cannot continue."
            exit 1
        }
        $env:AZURE_AI_FOUNDRY_ENDPOINT = $endpoint
    }
    Write-Ok "Endpoint: $env:AZURE_AI_FOUNDRY_ENDPOINT"

    # --- 3. Print A2A banner ---
    Write-Host ""
    Write-Host "  =================================================================" -ForegroundColor Magenta
    Write-Host "  |  SRE AGENT -- A2A SERVER                                      |" -ForegroundColor Magenta
    Write-Host "  =================================================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Status "Agent card:  http://${Host}:${Port}/.well-known/agent.json"
    Write-Status "JSON-RPC:    http://${Host}:${Port}/"
    Write-Host ""

    # --- 5. Launch the A2A server ---
    $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    Write-Status "Starting A2A server on ${Host}:${Port} ..."
    & $venvPython a2a_server.py --host $Host --port $Port
    $serverExit = $LASTEXITCODE

    if ($serverExit -eq 0) {
        Write-Ok "A2A server stopped normally."
    } else {
        Write-Err "A2A server exited with code $serverExit."
        exit $serverExit
    }
} finally {
    Pop-Location
}
