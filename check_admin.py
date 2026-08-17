import sqlite3

try:
    conn = sqlite3.connect('/home/pai/pai-hire/ats_phongvan.db')
    rows = conn.execute("SELECT * FROM users WHERE role='admin'").fetchall()
    print('Admins:', len(rows))
    for r in rows:
        print(r)
except Exception as e:
    print('Error:', e)
