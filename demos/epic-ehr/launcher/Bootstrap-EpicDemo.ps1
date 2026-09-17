[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'EpicDemo'),
    [string]$Repository = 'jochenvw/computer-use-demos',
    [switch]$SkipShortcut,
    [switch]$SkipPrerequisiteInstall
)

$ErrorActionPreference = 'Stop'
$launcherRoot = Join-Path $InstallRoot 'launcher'
$sharedRoot = Join-Path $InstallRoot 'shared'
foreach ($path in @($launcherRoot, $sharedRoot, (Join-Path $InstallRoot 'releases'), (Join-Path $InstallRoot 'staging'))) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}
$cosign = Get-Command cosign, cosign-windows-amd64 -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $SkipPrerequisiteInstall -and -not $cosign) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Install Sigstore cosign from a trusted package manager before bootstrapping.'
    }
    & $winget.Source install --id Sigstore.Cosign --exact --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Trusted cosign installation through WinGet failed.' }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start-EpicDemo.ps1') -Destination $launcherRoot -Force

$channels = Join-Path $launcherRoot 'channels.json'
if (-not (Test-Path -LiteralPath $channels)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'channels.json.example') -Destination $channels
}

$envFile = Join-Path $sharedRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    @"
API_BEARER_TOKEN=$([Convert]::ToBase64String($bytes))
EPIC_BACKEND=fixture
MODEL_DEPLOYMENT=gpt-6-astra
EPIC_AUDIT_PATH=$sharedRoot\audit.jsonl
EPIC_CACHE_TTL_SECONDS=900
EPIC_CACHE_MAX_ENTRIES=16
EPIC_CACHE_MAX_BYTES=8388608
"@ | Set-Content -LiteralPath $envFile -Encoding UTF8
    $acl = Get-Acl -LiteralPath $envFile
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity, 'FullControl', 'Allow'
    ))
    Set-Acl -LiteralPath $envFile -AclObject $acl
}

if (-not $SkipShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Start Epic Demo.lnk'))
    $shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcut.Arguments = "-NoProfile -NoExit -ExecutionPolicy RemoteSigned -File `"$launcherRoot\Start-EpicDemo.ps1`" -Mode RunInstalled -InstallRoot `"$InstallRoot`" -Repository `"$Repository`""
    $shortcut.WorkingDirectory = $launcherRoot
    $shortcut.Save()
}

Write-Output "Epic launcher ready at $launcherRoot. Bootstrap is idempotent; configuration remains in $sharedRoot."
