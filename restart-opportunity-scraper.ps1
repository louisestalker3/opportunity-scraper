<#
.SYNOPSIS
  Stop Opportunity Scraper scheduled tasks, kill runner-related processes,
  clear runner lock files, reset stuck DB rows, then start tasks again.

  Run from PowerShell (may need execution policy):
    .\restart-opportunity-scraper.ps1
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
. "$ProjectRoot\opportunity-scraper-common.ps1"

$Python = "C:\Users\louis\AppData\Local\Programs\Python\Python312\python.exe"
$Python = Resolve-OpportunityScraperPython -PreferredPath $Python

Write-Host "==> Stopping scheduled tasks..." -ForegroundColor Cyan
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

Write-Host "==> Starting scheduled tasks..." -ForegroundColor Cyan
Start-OpportunityScraperScheduledTasks

Write-Host "==> Task state:" -ForegroundColor Cyan
Show-OpportunityScraperScheduledTaskState

Write-Host "Done. If the DB reset failed, start PostgreSQL and run:" -ForegroundColor Green
Write-Host ('  cd backend; ' + $Python + ' scripts/reset_after_runner_restart.py') -ForegroundColor Gray
