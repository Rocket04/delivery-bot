# Настройка локальной БД (запускать ОДИН РАЗ, из PowerShell с правами администратора):
#   PowerShell (правый клик -> "Запуск от имени администратора")
#   & C:\Projects\delivery-bot\scripts\setup_db.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Запуск службы PostgreSQL 18 ===" -ForegroundColor Cyan
$svc = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "Служба postgresql-x64-18 не найдена. Проверь установку PostgreSQL 18." -ForegroundColor Red
    exit 1
}
if ($svc.Status -ne "Running") {
    Start-Service -Name "postgresql-x64-18"
    Start-Sleep -Seconds 2
}
Write-Host "  Служба запущена: $((Get-Service postgresql-x64-18).Status)"

Write-Host "=== 2. Пароль суперпользователя postgres ===" -ForegroundColor Cyan
Write-Host "  (тот, что ты вводил при установке PostgreSQL 18)"
$sec = Read-Host "Пароль" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)

$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

Write-Host "=== 3. Создание роли delivery ===" -ForegroundColor Cyan
& $psql -U postgres -h 127.0.0.1 -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'delivery') THEN CREATE ROLE delivery LOGIN PASSWORD 'delivery'; END IF; END \$\$;"
if ($LASTEXITCODE -ne 0) { Write-Host "  Ошибка создания роли — проверь пароль." -ForegroundColor Red; exit 1 }

Write-Host "=== 4. Создание базы delivery ===" -ForegroundColor Cyan
$exists = & $psql -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_database WHERE datname = 'delivery'"
if ($exists -eq "1") {
    Write-Host "  База delivery уже существует."
} else {
    & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres -h 127.0.0.1 -O delivery delivery
}

Write-Host ""
Write-Host "Готово! Роль delivery/delivery и база delivery созданы." -ForegroundColor Green
Write-Host "Дальше скажи боту 'готово' — он применит миграции и запустит бота."