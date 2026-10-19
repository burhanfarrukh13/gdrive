$password = 'admin123'
$S = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = "email=admin@driveaccess.local&password=" + $password
$null = Invoke-WebRequest -Uri "http://localhost:8000/login" -Method POST -Body $body -WebSession $S -UseBasicParsing -MaximumRedirection 0

Write-Host "=== TEST 1: Set price on the existing grants (Burhan has 4 grants on shopify+logo, no price yet) ==="
$ids = @(1,2,3,4)
foreach ($gid in $ids) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/fees/$gid/edit" -Method POST -Body "price_amount=2000&price_currency=PKR&fee_credit_account=Meezan+-+Qureshi" -WebSession $S -UseBasicParsing -MaximumRedirection 0
        Write-Host "  grant $gid -> Status $($r.StatusCode)"
    } catch {
        Write-Host "  grant $gid -> ERROR: $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "=== TEST 2: /revenue should now show 4 events with source 'Sale' ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/revenue" -WebSession $S -UseBasicParsing
Write-Host "Status: $($r.StatusCode)"
Write-Host "  has 'Synced from' badge: $([bool]($r.Content -like '*Synced from*'))"
Write-Host "  has 'Total Received' tile: $([bool]($r.Content -like '*Total Received*'))"
Write-Host "  has 'Sale' source label: $([bool]($r.Content -like '*Sale*'))"
Write-Host "  has 4 fee-synced rows: $(([regex]::Matches($r.Content, '>Sale<')).Count)"
Write-Host "  has 'Open a student and click' hint: $([bool]($r.Content -like '*Open a student*'))"

Write-Host ""
Write-Host "=== TEST 3: Mark one fee paid (id=1) -> revenue should become Received ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/fees/1/mark-paid" -Method POST -Body "paid_on=2026-07-28&credit_account=Meezan+-+Qureshi" -WebSession $S -UseBasicParsing -MaximumRedirection 0
Write-Host "Status: $($r.StatusCode)"

Write-Host ""
Write-Host "=== TEST 4: DB state after mark-paid ==="
# Use python for the DB peek since powershell chokes on unicode
python -c "
import sqlite3
c = sqlite3.connect(r'D:\claude\gdrive\gdrive-platform\data\app.db')
print('--- grants ---')
for r in c.execute('SELECT id,student_id,folder_id,price_amount,fee_status,fee_paid_on,fee_credit_account FROM access_grants ORDER BY id'):
    print(' ', r)
print('--- revenue events ---')
for r in c.execute('SELECT id,student_id,amount,currency,source,status,received_on,substr(notes,1,40) FROM revenue_events ORDER BY id'):
    print(' ', r)
"

Write-Host ""
Write-Host "=== TEST 5: /fees should show 'Sales & Revenue' as title and a paid row ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/fees" -WebSession $S -UseBasicParsing
Write-Host "Status: $($r.StatusCode)"
Write-Host "  has 'Sales & Revenue' heading: $([bool]($r.Content -match 'Sales\s*[<&]amp;]*\s*Revenue'))"
Write-Host "  Paid row count: $(([regex]::Matches($r.Content, '>Paid</span>')).Count)"

Write-Host ""
Write-Host "=== TEST 6: Sidebar should NOT have separate 'Revenue' link ==="
$r = Invoke-WebRequest -Uri "http://localhost:8000/dashboard" -WebSession $S -UseBasicParsing
Write-Host "Status: $($r.StatusCode)"
Write-Host "  has 'Sales & Revenue' link: $([bool]($r.Content -like '*Sales &amp; Revenue*'))"
Write-Host "  has old 'Fees' link: $([bool]($r.Content -match '>Fees</span>'))"
Write-Host "  has old separate Revenue link: $([bool]($r.Content -match '>Revenue</span>'))"
