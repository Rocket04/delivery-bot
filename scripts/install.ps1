# Install project dependencies into .venv (no admin needed).
# Uses uv; its cache lives inside the project because of sandbox limits.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"
$env:TMP = Join-Path $root ".tmp"
$env:TEMP = Join-Path $root ".tmp"

if (-not (Test-Path ".venv")) { uv venv .venv }
uv pip install --python .\.venv\Scripts\python.exe aiogram "sqlalchemy[asyncio]" asyncpg alembic "pydantic-settings>=2.4" pytest pytest-asyncio aiosqlite
Write-Host "Dependencies installed." -ForegroundColor Green