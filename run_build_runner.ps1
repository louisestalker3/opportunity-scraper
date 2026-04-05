$env:CLAUDE_BIN = "C:\Users\louis\AppData\Roaming\npm\claude.cmd"
$env:PATH = "C:\Users\louis\AppData\Roaming\npm;" + $env:PATH
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
. "$ProjectRoot\opportunity-scraper-common.ps1"
$Python = Resolve-OpportunityScraperPython -PreferredPath "C:\Users\louis\AppData\Local\Programs\Python\Python312\python.exe"
Set-Location $ProjectRoot
& $Python (Join-Path $ProjectRoot "build_runner.py")
