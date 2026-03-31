$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\louis\repos\opportunity-scraper"
$Python = "C:\Users\louis\AppData\Local\Programs\Python\Python312\python.exe"
$Npm = "C:\Program Files\nodejs\npm.cmd"

Write-Host "==> Stopping services..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName "OpportunityScraper-Backend"    -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "OpportunityScraper-Celery"     -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "OpportunityScraper-CeleryBeat" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "OpportunityScraper-Frontend"   -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host "==> Pulling latest code..." -ForegroundColor Cyan
Set-Location $ProjectRoot
git pull

Write-Host "==> Installing backend dependencies..." -ForegroundColor Cyan
& $Python -m pip install -r "$ProjectRoot\backend\requirements.txt" --quiet

Write-Host "==> Running database migrations..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"
& $Python -m alembic upgrade head

Write-Host "==> Installing frontend dependencies..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\frontend"
& $Npm install --silent

Write-Host "==> Starting services..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName "OpportunityScraper-Backend"
Start-ScheduledTask -TaskName "OpportunityScraper-Celery"
Start-ScheduledTask -TaskName "OpportunityScraper-CeleryBeat"
Start-ScheduledTask -TaskName "OpportunityScraper-Frontend"
Start-Sleep -Seconds 3

Write-Host "==> Status:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "OpportunityScraper-*" | Select-Object TaskName, State | Format-Table -AutoSize

Write-Host "Done." -ForegroundColor Green
