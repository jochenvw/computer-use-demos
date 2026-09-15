# setup.ps1 -- Bootstrap script for deploying the SRE agent on a fresh Windows VM.
# Idempotent: safe to run multiple times.

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SRE Agent -- Environment Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir

try {
    # -- Step 1: Ensure uv is installed ----------------------------------------
    Write-Host "[1/4] Checking for uv..." -ForegroundColor Cyan
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $uvVersion = (uv --version) 2>&1
        Write-Host "  uv is already installed ($uvVersion)" -ForegroundColor Green
    } else {
        Write-Host "  uv not found. Installing..." -ForegroundColor Yellow
        try {
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
            # Refresh PATH so the current session can find uv
            $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                throw "uv was installed but is not available on PATH. Please restart your shell and re-run this script."
            }
            Write-Host "  uv installed successfully." -ForegroundColor Green
        } catch {
            Write-Host "  ERROR: Failed to install uv -- $_" -ForegroundColor Red
            exit 1
        }
    }

    # -- Step 2: Sync dependencies ---------------------------------------------
    Write-Host "[2/4] Running uv sync..." -ForegroundColor Cyan
    uv sync
    Write-Host "  Dependencies synced." -ForegroundColor Green

    # -- Step 3: Validate venv & key imports -----------------------------------
    Write-Host "[3/4] Validating virtual environment..." -ForegroundColor Cyan
    $venvPath = Join-Path $scriptDir ".venv"
    if (-not (Test-Path $venvPath)) {
        throw "Virtual environment not found at $venvPath. uv sync may have failed."
    }

    uv run python -c "import azure.ai.projects; import pyautogui; import PIL; print('OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "Package import check failed. The virtual environment may be corrupt -- try removing .venv and re-running this script."
    }
    Write-Host "  All key packages are importable." -ForegroundColor Green

    # -- Step 4: Check for required environment variables ----------------------
    Write-Host "[4/4] Checking environment variables..." -ForegroundColor Cyan
    if ([string]::IsNullOrWhiteSpace($env:AZURE_AI_FOUNDRY_ENDPOINT)) {
        Write-Host "  WARNING: AZURE_AI_FOUNDRY_ENDPOINT is not set." -ForegroundColor Yellow
        Write-Host "  The SRE agent requires this variable to connect to Azure AI Foundry." -ForegroundColor Yellow
        Write-Host "  Set it before running the agent:" -ForegroundColor Yellow
        Write-Host '  $env:AZURE_AI_FOUNDRY_ENDPOINT = "https://<your-resource>.services.ai.azure.com"' -ForegroundColor Yellow
    } else {
        Write-Host "  AZURE_AI_FOUNDRY_ENDPOINT is set." -ForegroundColor Green
    }

    # -- Done ------------------------------------------------------------------
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Setup complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Ensure AZURE_AI_FOUNDRY_ENDPOINT is set (see above)." -ForegroundColor White
    Write-Host "  2. Log in to Azure:  az login" -ForegroundColor White
    Write-Host "  3. Run the agent:    uv run python main.py" -ForegroundColor White
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "Setup failed: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
