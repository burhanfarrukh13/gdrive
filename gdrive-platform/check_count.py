import sqlite3

c = sqlite3.connect(r'D:\claude\gdrive\gdrive-platform\data\app.db')
n_fee = c.execute("SELECT COUNT(*) FROM revenue_events WHERE source='fee'").fetchone()[0]
print(f'  fee-synced revenue events after 2 visits: {n_fee}')
print(f'  expected: 4 (one per priced grant)')
print(f'  {"OK" if n_fee == 4 else "DUPLICATES"}')

print()
print('=== Per-folder revenue totals ===')
for r in c.execute("""
    SELECT df.label,
           SUM(CASE WHEN re.status = 'received' THEN re.amount ELSE 0 END) AS received,
           SUM(CASE WHEN re.status = 'pending' THEN re.amount ELSE 0 END) AS pending,
           SUM(CASE WHEN re.status = 'cancelled' THEN re.amount ELSE 0 END) AS cancelled
    FROM revenue_events re
    LEFT JOIN access_grants ag ON re.notes LIKE 'grant:' || ag.id || '|%'
    LEFT JOIN drive_folders df ON ag.folder_id = df.id
    WHERE re.source = 'fee'
    GROUP BY df.label
"""):
    print(f'  {r[0]:20s}  received={r[1]:.0f}  pending={r[2]:.0f}  cancelled={r[3]:.0f}')

print()
print('=== Summary ===')
total_received = c.execute("SELECT COALESCE(SUM(amount),0) FROM revenue_events WHERE status='received'").fetchone()[0]
total_pending = c.execute("SELECT COALESCE(SUM(amount),0) FROM revenue_events WHERE status='pending'").fetchone()[0]
print(f'  Total revenue received (all): {total_received:.0f}')
print(f'  Total revenue pending (all): {total_pending:.0f}')
