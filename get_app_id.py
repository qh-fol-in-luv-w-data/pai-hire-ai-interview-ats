import sqlite3
import os

db_path = "ats_phongvan.db"
if not os.path.exists(db_path):
    print("DB not found at", db_path)
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, status FROM cv_applications WHERE status = 'evaluated' OR status = 'completed' LIMIT 5;")
    rows = cur.fetchall()
    if rows:
        print("Completed applications:")
        for r in rows:
            print(r)
    else:
        print("No completed applications found. Let's look for any app_id:")
        cur.execute("SELECT id, name, status FROM cv_applications LIMIT 5;")
        for r in cur.fetchall():
            print(r)
    
    print("\nLet's also check interview_sessions:")
    cur.execute("SELECT id, app_id, status FROM interview_sessions WHERE status = 'evaluated' OR status = 'completed' LIMIT 5;")
    for r in cur.fetchall():
        print(r)
