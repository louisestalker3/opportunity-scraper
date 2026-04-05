# Shared helpers for Opportunity Scraper PowerShell scripts (update, restart, run_build_runner).
# Dot-source from the repo root, e.g.:
#   $ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
#   . "$ProjectRoot\opportunity-scraper-common.ps1"

$script:OpportunityScraperScheduledTaskNames = @(
    "OpportunityScraper-Backend",
    "OpportunityScraper-Celery",
    "OpportunityScraper-CeleryBeat",
    "OpportunityScraper-Frontend",
    "OpportunityScraper-BuildRunner"
)

function Resolve-OpportunityScraperPython {
    param(
        [string]$PreferredPath = ""
    )
    if ($PreferredPath -and (Test-Path -LiteralPath $PreferredPath)) {
        return $PreferredPath
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python not found. Set `$PreferredPath in the calling script or ensure python is on PATH."
}

function Stop-OpportunityScraperScheduledTasks {
    foreach ($t in $script:OpportunityScraperScheduledTaskNames) {
        Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

function Stop-OpportunityScraperPythonRunners {
    Get-WmiObject Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*celery*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Get-WmiObject Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*uvicorn*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Get-WmiObject Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*build_runner*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

function Clear-OpportunityScraperRunnerLocks {
    param([Parameter(Mandatory)][string]$ProjectRoot)
    foreach ($pat in @(".task_lock_*", ".run_lock_*", ".build_lock_*")) {
        Get-ChildItem -Path $ProjectRoot -Filter $pat -Force -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                Write-Host "  removed $($_.Name)"
            }
    }
}

function Invoke-OpportunityScraperRunnerDbReset {
    param(
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$PythonExe
    )
    $resetScript = Join-Path $ProjectRoot "backend\scripts\reset_after_runner_restart.py"
    $out = & $PythonExe $resetScript 2>&1
    $out | Write-Host
    return $LASTEXITCODE
}

function Start-OpportunityScraperScheduledTasks {
    foreach ($t in $script:OpportunityScraperScheduledTaskNames) {
        Start-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
}

function Show-OpportunityScraperScheduledTaskState {
    Get-ScheduledTask -TaskName "OpportunityScraper-*" -ErrorAction SilentlyContinue |
        Select-Object TaskName, State |
        Format-Table -AutoSize
}
