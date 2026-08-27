# Установка зависимостей проекта в .venv (можно запускать без админа).
# Использует uv (его кэш лежит внутри проекта из-за ограничений песочницы).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"
$env:TMP = Join-Path $root ".tmp"
$env:TEMP = Join-Path $root ".tmp"

if (-not (Test-Path ".venv")) { uv venv .venv }
uv pip install --python .\.venv\Scripts\python.exe aiogram "sqlalchemy[asyncio]" asyncpg alembic "pydantic-settings>=2.4" pytest pytest-asyncio aiosqlite
Write-Host "Зависимости установлены." -ForegroundColor Green