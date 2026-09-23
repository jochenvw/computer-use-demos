<#
Moves the disconnected demo user's desktop session to the VM console so that
SSMS/Edge keep rendering and accepting input without an open RDP client.
Reconnecting RDP later simply takes the session back.
#>
param(
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$VmName = 'epicdemo-desktop-vm',
    [string]$Subscription = 'e3825c9a-4bce-43e1-899e-1610156c9383',
    [string]$UserName = 'demoadmin'
)
$ErrorActionPreference = 'Stop'
$script = @"
`$line = (qwinsta | Select-String '\s$UserName\s').Line
if (-not `$line) { 'No session for $UserName - log in over RDP once first.'; exit 1 }
`$id = [regex]::Match(`$line, '\s(\d+)\s+(Active|Disc|Conn)').Groups[1].Value
if (`$line -match 'Active' -and `$line -notmatch 'rdp-tcp') { "Session `$id already on console."; exit 0 }
tscon `$id /dest:console
Start-Sleep 2
qwinsta
"@
$file = Join-Path ([IO.Path]::GetTempPath()) 'keep-session-alive.remote.ps1'
Set-Content -Path $file -Value $script -Encoding UTF8
try {
    az vm run-command invoke -g $ResourceGroup -n $VmName --subscription $Subscription `
        --command-id RunPowerShellScript --scripts "@$file" --query 'value[0].message' -o tsv
} finally { Remove-Item $file -ErrorAction SilentlyContinue }
