param(
    [Parameter(Mandatory=$true)][string]$PrinterName,
    [string]$Origin = "https://erp.bm-kw.com",
    [int]$Port = 17777
)

$ErrorActionPreference = "Stop"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:ProgramData "POSNextLocalAgent"
$TaskName = "POSNext Local Agent"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force (Join-Path $SourceDir "POSNextLocalAgent.ps1") (Join-Path $InstallDir "POSNextLocalAgent.ps1")

$tokenBytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($tokenBytes) } finally { $rng.Dispose() }
$token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+','-').Replace('/','_')

$config = [ordered]@{
    BindHost = "127.0.0.1"
    Port = $Port
    Token = $token
    AllowedOrigins = @($Origin)
    AllowedPrinters = @($PrinterName)
}
$config | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $InstallDir "config.json")

$url = "http://127.0.0.1:$Port/"
& netsh http delete urlacl url=$url 2>$null | Out-Null
& netsh http add urlacl url=$url user="$env:USERDOMAIN\$env:USERNAME" | Out-Null

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$InstallDir\POSNextLocalAgent.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "POSNext loopback printer and cash drawer agent" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host ""
Write-Host "POSNext Local Agent installed." -ForegroundColor Green
Write-Host "Printer: $PrinterName"
Write-Host "Origin : $Origin"
Write-Host "URL    : $url"
Write-Host ""
Write-Host "Local Agent Token (paste this into POSNext -> Cash Drawer Setup):" -ForegroundColor Yellow
Write-Host $token -ForegroundColor Cyan
Write-Host ""
Write-Host "Keep this token private. It is stored in C:\ProgramData\POSNextLocalAgent\config.json and should only be entered on this POS terminal."
