import sqlite3

c = sqlite3.connect(r'D:\claude\gdrive\gdrive-platform\data\app.db')

print('=== TABLES ===')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    print(' ', r[0])

print()
print('=== SEEDED OWNER (auto-created on first run) ===')
for r in c.execute('SELECT id,email,role,is_active FROM users'):
    print(' ', r)

print()
print('=== ROW COUNTS ===')
for tbl in ['drive_folders', 'students', 'access_grants', 'revenue_events',
            'payouts', 'revenue_distributions', 'audit_logs', 'users']:
    n = c.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    print(f'  {tbl:25s} {n}')
