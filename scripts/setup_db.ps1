# One-time local DB setup for DeliveryBot (ASCII-only, works in PowerShell 5.1)
# RUN AS ADMINISTRATOR: right-click PowerShell -> "Run as administrator"
#   & C:\Projects\delivery-bot\scripts\setup_db.ps1

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: this script must run as Administrator." -ForegroundColor Red
    Write-Host "  1) Win+R, type: powershell, press Ctrl+Shift+Enter"
    Write-Host "  2) then run:  & C:\Projects\delivery-bot\scripts\setup_db.ps1"
    exit 1
}

Write-Host "=== 1. Start PostgreSQL 18 service ===" -ForegroundColor Cyan
$svc = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "ERROR: service postgresql-x64-18 not found. Is PostgreSQL 18 installed?" -ForegroundColor Red
    exit 1
}
if ($svc.Status -ne "Running") {
    Start-Service -Name "postgresql-x64-18"
    Start-Sleep -Seconds 3
}
Write-Host "  Service status: $((Get-Service postgresql-x64-18).Status)"

Write-Host "=== 2. Superuser 'postgres' password ===" -ForegroundColor Cyan
Write-Host "  (the one you entered when installing PostgreSQL 18)"
$sec = Read-Host "Password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)

$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

Write-Host "=== 3. Create role 'delivery' ===" -ForegroundColor Cyan
$roleExists = & $psql -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'delivery'"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: cannot connect to PostgreSQL. Wrong password?" -ForegroundColor Red
    exit 1
}
if ($roleExists -eq "1") {
    Write-Host "  Role 'delivery' already exists - OK."
} else {
    $sql = 'CREATE ROLE delivery LOGIN PASSWORD ''delivery'';'
    & $psql -U postgres -h 127.0.0.1 -v ON_ERROR_STOP=1 -c $sql
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: role creation failed." -ForegroundColor Red; exit 1 }
    Write-Host "  Role 'delivery' created."
}

Write-Host "=== 4. Create database 'delivery' ===" -ForegroundColor Cyan
$dbExists = & $psql -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_database WHERE datname = 'delivery'"
if ($dbExists -eq "1") {
    Write-Host "  Database 'delivery' already exists - OK."
} else {
    & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres -h 127.0.0.1 -O delivery delivery
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: database creation failed." -ForegroundColor Red; exit 1 }
    Write-Host "  Database 'delivery' created."
}

Write-Host ""
Write-Host "DONE. Role delivery/delivery + database delivery are ready." -ForegroundColor Green
Write-Host "Now write 'gotovo' to the bot in chat - it will run migrations and start the bot."