[CmdletBinding()]
param(
    [ValidateSet('run.ps1', 'live.ps1')][string]$Script = 'run.ps1',
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [switch]$KeepAlive,
    [string]$TerminalRoot = 'C:\DemoTools\terminal'
)
# Opens the agent console in Windows Terminal (zoomable, truecolor, large font) with the
# versioned profile in terminal\settings.json. Falls back to a classic console window.

$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot $Script
$arguments = @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'RemoteSigned', '-File', "`"$target`"", '-Port', "$Port")
if ($KeepAlive) { $arguments += '-KeepAlive' }

$wt = Get-ChildItem -LiteralPath $TerminalRoot -Recurse -Filter 'wt.exe' -File -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $wt) {
    Write-Warning "Windows Terminal not found under $TerminalRoot; using a classic console window."
    $process = Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -PassThru
    # Keep the caller (a scheduled task) alive for as long as the agent runs.
    $process.WaitForExit()
    exit $process.ExitCode
}

# Portable mode reads settings\settings.json next to wt.exe.
$terminalHome = $wt.DirectoryName
New-Item -ItemType File -Path (Join-Path $terminalHome '.portable') -Force | Out-Null
$settings = Join-Path $terminalHome 'settings'
New-Item -ItemType Directory -Path $settings -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'terminal\settings.json') -Destination (Join-Path $settings 'settings.json') -Force

# One named window: a relaunch adds a tab there instead of opening another window.
$wtArguments = @('-w', 'clinical-agent', 'new-tab', '--profile', '{7d4c2f5a-5a3e-4c1b-9d0e-3f6b1a2c8e41}',
    '--title', '"Clinical data agent"', '-d', "`"$PSScriptRoot`"", 'powershell.exe') + $arguments
Start-Process -FilePath $wt.FullName -ArgumentList $wtArguments -WorkingDirectory $PSScriptRoot
