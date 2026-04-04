$env:CLAUDE_BIN = "C:\Users\louis\AppData\Roaming\npm\claude.cmd"
$env:PATH = "C:\Users\louis\AppData\Roaming\npm;" + $env:PATH
Set-Location "C:\Users\louis\repos\opportunity-scraper"
& "C:\Users\louis\AppData\Local\Programs\Python\Python312\python.exe" build_runner.py
