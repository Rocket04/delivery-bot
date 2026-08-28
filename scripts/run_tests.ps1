# Full test run: regular + PG integration tests (when PG_TEST_URL is set).
# Usage:
#   .\scripts\run_tests.ps1                              # regular only (PG skipped)
#   .\scripts\run_tests.ps1 -PGUrl "postgresql+asyncpg://postgres@127.0.0.1:55432/delivery_test"
param(
    [string]$PGUrl = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"
if ($PGUrl) {
    $env:PG_TEST_URL = $PGUrl
    Write-Host "PG_TEST_URL set - PG integration tests active"
} else {
    Remove-Item Env:PG_TEST_URL -ErrorAction SilentlyContinue
}
& .\.venv\Scripts\python.exe -m pytest -q
exit $LASTEXITCODE