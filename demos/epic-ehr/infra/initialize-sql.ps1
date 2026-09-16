[CmdletBinding()]
param([string]$AdminUser, [string]$AdminPassword, [string]$ExpectedPasswordHash)

$ErrorActionPreference = 'Stop'
$token = [IntPtr]::Zero
$impersonation = $null
if ($AdminPassword) {
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $receivedHash = [Convert]::ToBase64String($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($AdminPassword)))
    } finally { $hash.Dispose() }
    if (-not $ExpectedPasswordHash -or $receivedHash -cne $ExpectedPasswordHash) {
        throw 'Administrator credential transport integrity check failed.'
    }
    $account = Get-LocalUser -Name $AdminUser -ErrorAction Stop
    if (-not $account.Enabled) { throw 'The requested VM administrator account is disabled.' }
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DemoSqlLogon {
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool LogonUser(string user, string domain, string password, int type, int provider, out IntPtr token);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr token);
}
'@
    if (-not [DemoSqlLogon]::LogonUser($AdminUser, '.', $AdminPassword, 2, 0, [ref]$token)) {
        throw "VM administrator logon failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())."
    }
    $AdminPassword = $null
    # SQL Windows authentication needs the actual administrator token, not Run Command's SYSTEM identity.
    $impersonation = [Security.Principal.WindowsIdentity]::Impersonate($token)
}
Add-Type -AssemblyName System.Data
$connection = [System.Data.SqlClient.SqlConnection]::new(
    'Server=localhost;Integrated Security=True;Encrypt=True;TrustServerCertificate=True;Connection Timeout=30'
)
try {
    $connection.Open()
    $command = $connection.CreateCommand()
    $command.CommandTimeout = 120
    $command.CommandText = "SELECT IS_SRVROLEMEMBER('sysadmin')"
    if ($command.ExecuteScalar() -ne 1) {
        throw 'SQL setup requires the VM administrator SQL login, not the Run Command SYSTEM identity.'
    }
    $command.CommandText = @'
IF DB_ID(N'EpicDemo') IS NULL CREATE DATABASE EpicDemo;
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;
EXEC sp_configure 'max server memory (MB)', 8192;
RECONFIGURE;
'@
    $command.ExecuteNonQuery() | Out-Null
    $connection.ChangeDatabase('EpicDemo')
    $command.CommandText = @'
IF OBJECT_ID(N'dbo.Patients', N'U') IS NULL
CREATE TABLE dbo.Patients (PatientId nvarchar(64) NOT NULL PRIMARY KEY, DisplayName nvarchar(100) NOT NULL, Synthetic bit NOT NULL);
IF OBJECT_ID(N'dbo.Observations', N'U') IS NULL
CREATE TABLE dbo.Observations (ObservationId int NOT NULL PRIMARY KEY, PatientId nvarchar(64) NOT NULL REFERENCES dbo.Patients(PatientId),
    LoincCode nvarchar(20) NOT NULL, Description nvarchar(100) NOT NULL, NumericValue decimal(10,2) NOT NULL,
    Unit nvarchar(20) NOT NULL, RecordedAt datetime2 NOT NULL);
IF NOT EXISTS (SELECT 1 FROM dbo.Patients WHERE PatientId=N'DEMO-100042')
INSERT dbo.Patients VALUES (N'DEMO-100042', N'Jamie Rivera (synthetic)', 1);
IF NOT EXISTS (SELECT 1 FROM dbo.Observations WHERE ObservationId=1)
INSERT dbo.Observations VALUES (1,N'DEMO-100042',N'8480-6',N'Synthetic systolic blood pressure',120,N'mm[Hg]','2026-09-10T09:10:00');
IF NOT EXISTS (SELECT 1 FROM dbo.Observations WHERE ObservationId=2)
INSERT dbo.Observations VALUES (2,N'DEMO-100042',N'8462-4',N'Synthetic diastolic blood pressure',80,N'mm[Hg]','2026-09-10T09:10:00');
'@
    $command.ExecuteNonQuery() | Out-Null
    $command.CommandText = 'SELECT COUNT(*) FROM dbo.Observations WHERE PatientId = N''DEMO-100042'''
    $count = $command.ExecuteScalar()
    $command.Dispose()
} finally {
    $connection.Dispose()
    if ($impersonation) { $impersonation.Undo(); $impersonation.Dispose() }
    if ($token -ne [IntPtr]::Zero) { [DemoSqlLogon]::CloseHandle($token) | Out-Null }
}
@{ database = 'EpicDemo'; synthetic = $true; observations = $count } |
    ConvertTo-Json | Set-Content -LiteralPath 'C:\DemoTools\sql-database-status.json' -Encoding UTF8
Write-Output ("EpicDemo synthetic database ready; observation rows: " + $count)
