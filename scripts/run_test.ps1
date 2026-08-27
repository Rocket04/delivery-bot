# run_test.ps1 — тестовый инстанс для экспериментов (по PLAN.md «Тестовое окружение»).
#
# Модель (решение владельца 2026-08-28): main = стабильная; эксперименты — ветки exp/*;
# быстрые эксперименты гоняются на тестовом боте из @BotFather с отдельной БД delivery_test.
# Прод-токен и прод-БД этот скрипт НЕ трогает.
#
# Примеры:
#   .\scripts\run_test.ps1 -TestsOnly                    # только юнит-тесты (SQLite in-memory)
#   .\scripts\run_test.ps1 -BotToken "123456:AA..."      # миграции + запуск тестового бота
#   .\scripts\run_test.ps1 -BotToken "123456:AA..." -MigrateOnly
#
# Требования: локальный PostgreSQL 18 (служба postgresql-x64-18), venv (.venv создастся сам)
param(
    [string]$BotToken = "",
    [switch]$TestsOnly,
    [switch]$MigrateOnly,
    [string]$DbName = "delivery_test"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# 1. Окружение
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "venv не найден — создаю через uv..."
    uv venv .venv
    & .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"
}

$Py = ".\.venv\Scripts\python.exe"

# 2. Режим: только тесты
if ($TestsOnly) {
    Write-Host "==> pytest (юнит, SQLite in-memory)"
    & $Py -m pytest -q
    exit $LASTEXITCODE
}

if (-not $BotToken) {
    Write-Error "Укажи -BotToken (токен тестового бота из @BotFather) или -TestsOnly"
    exit 1
}

# 3. Тестовая БД delivery_test в локальном PostgreSQL
$env:DB_URL = "postgresql+asyncpg://delivery:delivery@localhost:5432/$DbName"
Write-Host "==> Тестовая БД: $DbName ($env:DB_URL)"
Write-Host "    Если PostgreSQL не запущен: служба postgresql-x64-18 (запуск от администратора)."

& $Py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($MigrateOnly) { Write-Host "Миграции применены. Бот не запускаем (-MigrateOnly)."; exit 0 }

# 4. Запуск тестового бота (токен только в env процесса — в .env и репозиторий не пишем)
$env:BOT_TOKEN = $BotToken
Write-Host "==> Старт тестового бота (Ctrl+C для остановки)"
& $Py -m bot