$password = 'admin123'
$S = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$null = Invoke-WebRequest -Uri "http://localhost:8000/login" -Method POST -Body "email=admin@driveaccess.local&password=$password" -WebSession $S -UseBasicParsing -MaximumRedirection 0
Write-Host "Cookies set:"
$S.Cookies.GetCookies("http://localhost:8000") | ForEach-Object { Write-Host "  $($_.Name)" }

Write-Host ""
$r = Invoke-WebRequest -Uri "http://localhost:8000/students/1" -WebSession $S -UseBasicParsing
Write-Host "Student page status:" $r.StatusCode
Write-Host "  has 'Sell access' title:" ($r.Content -like "*Sell access*")
Write-Host "  has 'Sale details' section:" ($r.Content -like "*Sale details*")
Write-Host "  has 'no price set' on existing grants:" ($r.Content -like "*no price set*")
Write-Host "  has shopify default price attr:" ($r.Content -match 'data-default-price="2000"')

Write-Host ""
Write-Host "=== /fees page ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/fees" -WebSession $S -UseBasicParsing
Write-Host "Status:" $r.StatusCode
Write-Host "  has 'no price set' badge:" ($r.Content -like "*no price set*")
Write-Host "  has 'Only show missing price' filter:" ($r.Content -like "*Only show missing price*")
Write-Host "  grant count rendered:" ([regex]::Matches($r.Content, 'href="/students/1"').Count)
