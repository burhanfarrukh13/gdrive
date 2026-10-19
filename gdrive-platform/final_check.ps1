$password = 'admin123'
$S = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = "email=admin@driveaccess.local&password=$password"
$null = Invoke-WebRequest -Uri "http://localhost:8000/login" -Method POST -Body $body -WebSession $S -UseBasicParsing -MaximumRedirection 0

Write-Host "=== Dashboard tiles ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/dashboard" -WebSession $S -UseBasicParsing
Write-Host "Status: $($r.StatusCode)"

# Extract just the tile values
$matches = [regex]::Matches($r.Content, 'text-3xl font-semibold[^>]*>([^<]+)<')
Write-Host "Tile values found:"
foreach ($m in $matches) { Write-Host "  -> $($m.Groups[1].Value.Trim())" }

Write-Host ""
Write-Host "=== Verify 'Revenue Received' tile shows 6000 (3 paid × 2000) ==="
Write-Host "  contains '6000': $([bool]($r.Content -match '\b6000\b'))"

Write-Host ""
Write-Host "=== /payouts page should be empty since no teams configured ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/payouts" -WebSession $S -UseBasicParsing
Write-Host "Status: $($r.StatusCode)"
Write-Host "  has 'Total Pending' tile: $([bool]($r.Content -like '*Total Pending*'))"
Write-Host "  has 'Team pending balances' header: $([bool]($r.Content -like '*Team pending balances*'))"

Write-Host ""
Write-Host "=== Legacy /revenue/new endpoint should redirect to /students ==="
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/revenue/new" -Method POST -Body "amount=100" -WebSession $S -UseBasicParsing -MaximumRedirection 0
    Write-Host "  Status: $($r.StatusCode), Location: $($r.Headers.Location)"
} catch {
    Write-Host "  Status: $($_.Exception.Response.StatusCode.value__)"
}

Write-Host ""
Write-Host "=== Backfill safety: hitting /revenue twice shouldn't duplicate ==="
$null = Invoke-WebRequest -Uri "http://localhost:8000/revenue" -WebSession $S -UseBasicParsing
$null = Invoke-WebRequest -Uri "http://localhost:8000/revenue" -WebSession $S -UseBasicParsing
python D:\claude\gdrive\gdrive-platform\check_count.py
