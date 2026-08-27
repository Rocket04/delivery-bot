# Применить миграции и запустить бота.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = ".\.venv\Scripts\python.exe"
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host "Миграции не применились — БД запущена? (см. setup_db.ps1)" -ForegroundColor Red; exit 1 }
& $py -m bot