<#
.SYNOPSIS
  Full Opportunity Scraper maintenance: stop stack, kill stray runners, clear lock files,
  reset stuck DB rows, pull code, install deps, migrate, then start scheduled tasks.

  Same safety steps as restart-opportunity-scraper.ps1, plus git pull / pip / alembic / npm.
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
. "$ProjectRoot\opportunity-scraper-common.ps1"

$Python = "C:\Users\louis\AppData\Local\Programs\Python\Python312\python.exe"
$Python = Resolve-OpportunityScraperPython -PreferredPath $Python
$Npm = "C:\Program Files\nodejs\npm.cmd"
$env:PATH = "C:\Users\louis\AppData\Roaming\npm;" + $env:PATH

Write-Host "==> Stopping services..." -ForegroundColor Cyan
Stop-OpportunityScraperScheduledTasks

Write-Host "==> Killing leftover Python workers (celery, uvicorn, build_runner)..." -ForegroundColor Cyan
Stop-OpportunityScraperPythonRunners

Write-Host "==> Removing runner lock files in repo root..." -ForegroundColor Cyan
Clear-OpportunityScraperRunnerLocks -ProjectRoot $ProjectRoot

Write-Host "==> Resetting stuck tasks / pipeline rows in PostgreSQL..." -ForegroundColor Cyan
$code = Invoke-OpportunityScraperRunnerDbReset -ProjectRoot $ProjectRoot -PythonExe $Python
if ($code -ne 0) {
    Write-Host "  WARNING: DB reset exited $code - is PostgreSQL running and DATABASE_URL correct in backend/.env?" -ForegroundColor Yellow
}

Write-Host "==> Pulling latest code..." -ForegroundColor Cyan
Set-Location $ProjectRoot
git pull

Write-Host "==> Installing backend dependencies..." -ForegroundColor Cyan
& $Python -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt") --quiet

Write-Host "==> Running database migrations..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
& $Python -m alembic upgrade head

Write-Host "==> Installing frontend dependencies..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "frontend")
& $Npm install --silent

Write-Host "==> Starting services..." -ForegroundColor Cyan
Start-OpportunityScraperScheduledTasks

Write-Host "==> Status:" -ForegroundColor Cyan
Show-OpportunityScraperScheduledTaskState

Write-Host "Done." -ForegroundColor Green
