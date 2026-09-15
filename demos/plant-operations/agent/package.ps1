<#
.SYNOPSIS
    Packages the SRE agent into a deployable zip file.
.DESCRIPTION
    Creates sre_agent.zip containing everything needed to deploy on a fresh
    Windows VM. Excludes .venv, __pycache__, .env, and other dev artifacts.
#>

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$OutputZip = Join-Path (Split-Path -Parent $ScriptDir) "sre_agent.zip"

Write-Host ""
Write-Host "Packaging SRE Agent..." -ForegroundColor Cyan

# Remove existing zip if present
if (Test-Path $OutputZip) {
    Remove-Item $OutputZip -Force
    Write-Host "  Removed existing $OutputZip" -ForegroundColor Yellow
}

# Build list of files to include
$include = @(
    "*.py",
    "*.toml",
    "*.lock",
    "*.md",
    "*.ps1",
    "*.bat",
    ".env.example",
    ".gitignore"
)

# Create a temp staging directory
$staging = Join-Path $env:TEMP "sre_agent_staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
$destDir = Join-Path $staging "sre_agent"
New-Item -ItemType Directory -Path $destDir | Out-Null

# Copy matching files
foreach ($pattern in $include) {
    Get-ChildItem -Path $ScriptDir -Filter $pattern -File | ForEach-Object {
        Copy-Item $_.FullName -Destination $destDir
        Write-Host "  + $($_.Name)" -ForegroundColor Green
    }
}

# Create the zip
Compress-Archive -Path $destDir -DestinationPath $OutputZip -Force

# Clean up staging
Remove-Item $staging -Recurse -Force

$zipSize = (Get-Item $OutputZip).Length / 1KB
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Package created: $OutputZip" -ForegroundColor Green
Write-Host "  Size: $([math]::Round($zipSize, 1)) KB" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Deploy to a Windows VM:" -ForegroundColor Cyan
Write-Host "  1. Copy sre_agent.zip to the VM" -ForegroundColor White
Write-Host "  2. Extract:    Expand-Archive sre_agent.zip -DestinationPath ." -ForegroundColor White
Write-Host "  3. Setup:      cd sre_agent; .\setup.ps1" -ForegroundColor White
Write-Host "  4. Configure:  Copy .env.example to .env and set your endpoint" -ForegroundColor White
Write-Host "  5. Run:        .\run.ps1   (or double-click run.bat)" -ForegroundColor White
Write-Host ""
