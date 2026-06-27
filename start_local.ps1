# Engram — one-click local launcher (Windows PowerShell)
#
#   Right-click -> Run with PowerShell, or:  ./start_local.ps1
#
# Starts (if needed) Postgres+Qdrant, applies migrations, seeds the bootstrap
# tenant, then launches the API and the web dashboard in their own windows and
# opens the browser.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1) Ensure config exists (default to the no-Docker local profile).
if (-not (Test-Path .env.local)) {
    Write-Host "No .env.local found - copying the no-Docker template." -ForegroundColor Yellow
    Copy-Item .env.local.example-no-docker .env.local
}

$envText = Get-Content .env.local -Raw

# 2) If using real Postgres + Docker is present, bring infra up.
if ($envText -match "postgresql") {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "Starting Postgres + Qdrant (docker compose)..." -ForegroundColor Cyan
        docker compose up -d | Out-Null
        Start-Sleep -Seconds 5
    } else {
        Write-Host "DATABASE_URL is Postgres but Docker isn't installed." -ForegroundColor Yellow
        Write-Host "Switch to no-Docker mode:  Copy-Item .env.local.example-no-docker .env.local" -ForegroundColor Yellow
    }
}

# 3) Schema + bootstrap tenant/collection.
Write-Host "Applying migrations + bootstrap..." -ForegroundColor Cyan
python -m alembic upgrade head
python -m engram.cli bootstrap

# 4) Read the API key to show the user.
$key = "local-dev-key"
$m = Select-String -Path .env.local -Pattern '^\s*ENGRAM_BOOTSTRAP_API_KEY\s*=\s*(.+)$'
if ($m) { $key = $m.Matches[0].Groups[1].Value.Trim() }

# 5) Launch API + dashboard in their own windows.
Write-Host "Launching API (8000) and dashboard (5500)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$PSScriptRoot'; python -m engram.cli serve"
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$PSScriptRoot'; python -m http.server 5500 --directory web"
Start-Sleep -Seconds 2
Start-Process "http://localhost:5500"

Write-Host ""
Write-Host "Engram is up:" -ForegroundColor Green
Write-Host "  API        -> http://localhost:8000/docs"
Write-Host "  Dashboard  -> http://localhost:5500"
Write-Host "  In the dashboard Settings: API URL http://localhost:8000  |  API Key  $key"
Write-Host ""
Write-Host "Tip: load sample data with  python scripts/seed_demo_api.py" -ForegroundColor DarkGray
