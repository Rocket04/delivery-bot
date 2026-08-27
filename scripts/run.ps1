# Apply migrations and start the bot (long polling).
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "ERROR: .venv not found. Run scripts\install.ps1 first." -ForegroundColor Red
    exit 1
}

& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: migrations failed. Is PostgreSQL running? (see scripts\setup_db.ps1)" -ForegroundColor Red
    exit 1
}

& $py -m bot