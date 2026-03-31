netsh advfirewall firewall add rule name="OpportunityScraper-Backend" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="OpportunityScraper-Frontend" dir=in action=allow protocol=TCP localport=5173
netsh advfirewall firewall add rule name="OpportunityScraper-PostgreSQL" dir=in action=allow protocol=TCP localport=5432
netsh advfirewall firewall add rule name="OpportunityScraper-Redis" dir=in action=allow protocol=TCP localport=6379
Write-Host "Firewall rules added." -ForegroundColor Green
