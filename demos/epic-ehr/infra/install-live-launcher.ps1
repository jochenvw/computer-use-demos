[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$LauncherContent,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedSha256
)

$ErrorActionPreference = 'Stop'
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $actualSha256 = [BitConverter]::ToString(
        $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($LauncherContent))
    ).Replace('-', '')
} finally {
    $sha256.Dispose()
}
if ($actualSha256 -ne $ExpectedSha256.ToUpperInvariant()) {
    throw 'Live launcher content hash mismatch.'
}

$service = 'C:\EpicDemo\service'
$launcher = Join-Path $service 'live.ps1'
$encoding = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($launcher, $LauncherContent, $encoding)
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut("$env:PUBLIC\Desktop\Epic Live Demo.lnk")
$link.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$link.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$service\agent-terminal.ps1`" -Script live.ps1"
$link.WorkingDirectory = $service
$link.Save()
Write-Output 'Epic Live Demo desktop shortcut installed.'
