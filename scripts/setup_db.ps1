# One-time local DB setup for DeliveryBot (ASCII-only, works in PowerShell 5.1)
# No admin needed while PostgreSQL is already running on port 5432.
# If it is NOT running, run this from an ADMIN PowerShell so it can start the service.

$ErrorActionPreference = "Stop"
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

Write-Host "=== 1. Check PostgreSQL on 5432 ===" -ForegroundColor Cyan
$probe = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue
if ($probe.TcpTestSucceeded) {
    Write-Host "  PostgreSQL is already running - good."
} else {
    Write-Host "  PostgreSQL is NOT running. Trying to start the service..." -ForegroundColor Yellow
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host "  ERROR: starting the service needs Administrator rights." -ForegroundColor Red
        Write-Host "  Run this script from an ADMIN PowerShell (right-click -> Run as administrator)" -ForegroundColor Yellow
        Write-Host "  or start the service manually: Win+R -> services.msc -> postgresql-x64-18 -> Start" -ForegroundColor Yellow
        exit 1
    }
    $svc = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "  ERROR: service postgresql-x64-18 not found. Is PostgreSQL 18 installed?" -ForegroundColor Red
        exit 1
    }
    Start-Service -Name "postgresql-x64-18"
    Start-Sleep -Seconds 3
    $probe2 = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue
    if (-not $probe2.TcpTestSucceeded) {
        Write-Host "  ERROR: service started but port 5432 is still closed. Check Windows Event Log (eventvwr)." -ForegroundColor Red
        exit 1
    }
    Write-Host "  PostgreSQL service started."
}

Write-Host "=== 2. Superuser 'postgres' password ===" -ForegroundColor Cyan
Write-Host "  (the one you entered when installing PostgreSQL 18)"
$sec = Read-Host "Password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)

Write-Host "=== 3. Create role 'delivery' (if missing) ===" -ForegroundColor Cyan
$roleExists = & $psql -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'delivery'"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: cannot connect to PostgreSQL. Wrong password?" -ForegroundColor Red
    exit 1
}
if ($roleExists -eq "1") {
    Write-Host "  Role 'delivery' already exists - OK."
} else {
    $sql = 'CREATE ROLE delivery LOGIN PASSWORD ''delivery'';'
    & $psql -U postgres -h 127.0.0.1 -v ON_ERROR_STOP=1 -c $sql
    if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: role creation failed." -ForegroundColor Red; exit 1 }
    Write-Host "  Role 'delivery' created."
}

Write-Host "=== 4. Create database 'delivery' (if missing) ===" -ForegroundColor Cyan
$dbExists = & $psql -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_database WHERE datname = 'delivery'"
if ($dbExists -eq "1") {
    Write-Host "  Database 'delivery' already exists - OK."
} else {
    & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres -h 127.0.0.1 -O delivery delivery
    if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: database creation failed." -ForegroundColor Red; exit 1 }
    Write-Host "  Database 'delivery' created."
}

Write-Host ""
Write-Host "DONE. Role delivery/delivery + database delivery are ready." -ForegroundColor Green
Write-Host "Now write 'gotovo' to the bot in chat - it will run migrations and start the bot."