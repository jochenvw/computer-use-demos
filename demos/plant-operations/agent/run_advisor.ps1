<#
.SYNOPSIS
    Launches the Maintenance Advisor — Incident Pattern Monitor.
.DESCRIPTION
    Watches the SRE agent's memory.json for new incidents and uses GPT-5.4
    to analyze patterns and recommend preventive maintenance.
#>

# --- Colored output helpers ---
function Write-Status  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Err     { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }

trap {
    Write-Host "`n[!] Interrupted -- shutting down." -ForegroundColor Yellow
    exit 130
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $ScriptDir

try {
    if (-not (Test-Path ".venv")) {
        Write-Err "Virtual environment not found (.venv)."
        Write-Err "Run setup.ps1 first:  .\setup.ps1"
        exit 1
    }
    Write-Ok "Virtual environment found."

    # Load .env
    if (Test-Path ".env") {
        Write-Status "Loading configuration from .env ..."
        Get-Content ".env" | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $eqIdx = $line.IndexOf("=")
                if ($eqIdx -gt 0) {
                    $key   = $line.Substring(0, $eqIdx).Trim()
                    $value = $line.Substring($eqIdx + 1).Trim()
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

    if (-not $env:AZURE_AI_FOUNDRY_ENDPOINT) {
        $endpoint = Read-Host "Enter your Azure AI Foundry endpoint URL"
        if (-not $endpoint) {
            Write-Err "No endpoint provided -- cannot continue."
            exit 1
        }
        $env:AZURE_AI_FOUNDRY_ENDPOINT = $endpoint
    }
    Write-Ok "Endpoint: $env:AZURE_AI_FOUNDRY_ENDPOINT"

    Write-Status "Starting Maintenance Advisor ..."
    $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    & $venvPython maintenance_advisor.py
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0 -and $exitCode -ne 130) {
        Write-Err "Advisor exited with code $exitCode."
        exit $exitCode
    }
} finally {
    Pop-Location
}
