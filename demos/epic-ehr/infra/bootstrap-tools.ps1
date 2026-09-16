[CmdletBinding()]
param([string]$ToolsRoot = 'C:\DemoTools')

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Path $ToolsRoot -Force | Out-Null
Set-Service -Name seclogon -StartupType Manual
Start-Service -Name seclogon

function Assert-MicrosoftSignature([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "Microsoft installer signature validation failed: $Path"
    }
}

function Install-Executable([string]$Path, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Path -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit(1800000)) {
        throw "Installer did not finish within 30 minutes. Inspect owned process $($process.Id)."
    }
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Installer failed with exit code $($process.ExitCode): $Path"
    }
}

$uvRoot = Join-Path $ToolsRoot 'uv'
$uv = Join-Path $uvRoot 'uv.exe'
if (-not (Test-Path -LiteralPath $uv)) {
    $release = Invoke-RestMethod 'https://api.github.com/repos/astral-sh/uv/releases/tags/0.11.17'
    $asset = @($release.assets | Where-Object name -eq 'uv-x86_64-pc-windows-msvc.zip')
    if ($asset.Count -ne 1 -or $asset[0].digest -notmatch '^sha256:[a-f0-9]{64}$') {
        throw 'The pinned uv release does not provide the expected SHA-256 asset digest.'
    }
    $archive = Join-Path $ToolsRoot 'uv-install.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $asset[0].browser_download_url -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $asset[0].digest.Substring(7)) {
        throw 'uv archive checksum mismatch.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $uvRoot -Force
    Remove-Item -LiteralPath $archive
}
if (-not (Test-Path -LiteralPath $uv)) { throw 'uv installation was not found.' }
$pythonRoot = Join-Path $ToolsRoot 'python'
[Environment]::SetEnvironmentVariable('UV_PYTHON_INSTALL_DIR', $pythonRoot, 'Machine')
$env:UV_PYTHON_INSTALL_DIR = $pythonRoot
& $uv python install 3.13 --quiet
if ($LASTEXITCODE -ne 0) { throw 'Managed Python installation failed.' }

$tunnelRoot = Join-Path $ToolsRoot 'devtunnel'
New-Item -ItemType Directory -Path $tunnelRoot -Force | Out-Null
$tunnel = Join-Path $tunnelRoot 'devtunnel.exe'
if (-not (Test-Path -LiteralPath $tunnel)) {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/TunnelsCliDownload/win-x64' -OutFile $tunnel
}
Assert-MicrosoftSignature $tunnel

$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
foreach ($entry in @($uvRoot, $tunnelRoot)) {
    if ($entry -notin $machinePath.Split(';')) { $machinePath += ";$entry" }
}
[Environment]::SetEnvironmentVariable('Path', $machinePath, 'Machine')
$env:Path = $machinePath + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edge)) {
    $products = Invoke-RestMethod 'https://edgeupdates.microsoft.com/api/products?view=enterprise'
    $stable = @($products | Where-Object Product -eq 'Stable')[0]
    $windows = @($stable.Releases | Where-Object { $_.Platform -eq 'Windows' -and $_.Architecture -eq 'x64' })[0]
    $msi = @($windows.Artifacts | Where-Object ArtifactName -eq 'msi')[0]
    if (-not $msi.Location) { throw 'No stable Windows x64 Edge installer was found.' }
    $installer = Join-Path $ToolsRoot 'MicrosoftEdgeEnterpriseX64.msi'
    Invoke-WebRequest -UseBasicParsing -Uri $msi.Location -OutFile $installer
    Assert-MicrosoftSignature $installer
    Install-Executable 'msiexec.exe' @('/i', "`"$installer`"", '/qn', '/norestart')
    Remove-Item -LiteralPath $installer
}
if (-not (Test-Path -LiteralPath $edge)) { throw 'Edge installation was not found.' }

$ssmsCandidates = @(
    "$ToolsRoot\SSMS22\Common7\IDE\Ssms.exe",
    "$env:ProgramFiles\Microsoft SQL Server Management Studio 22\Release\Common7\IDE\Ssms.exe",
    "${env:ProgramFiles(x86)}\Microsoft SQL Server Management Studio 20\Common7\IDE\Ssms.exe",
    "${env:ProgramFiles(x86)}\Microsoft SQL Server Management Studio 19\Common7\IDE\Ssms.exe",
    "${env:ProgramFiles(x86)}\Microsoft SQL Server Management Studio 18\Common7\IDE\Ssms.exe"
)
$ssms = $ssmsCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $ssms) {
    $installer = Join-Path $ToolsRoot 'vs_SSMS.exe'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/ssms/22/release/vs_SSMS.exe' -OutFile $installer
    Assert-MicrosoftSignature $installer
    Install-Executable $installer @('--installPath', "$ToolsRoot\SSMS22", '--quiet', '--wait', '--norestart', '--addProductLang', 'en-US')
    Remove-Item -LiteralPath $installer
    $ssms = $ssmsCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $ssms) { throw 'SSMS installation was not found.' }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$env:PUBLIC\Desktop\SQL Server Management Studio.lnk")
$shortcut.TargetPath = $ssms
$shortcut.Save()
[ordered]@{ uv = $uv; edge = $edge; ssms = $ssms } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ToolsRoot 'bootstrap-status.json') -Encoding UTF8
Write-Output 'Demo tools are ready. Run initialize-sql.ps1 as the VM administrator to seed the synthetic database.'
