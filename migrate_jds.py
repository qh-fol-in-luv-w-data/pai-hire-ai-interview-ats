import os
import sqlite3
import time
from pathlib import Path
from backend.config import JDS_DIR, CATEGORY_LABELS

def migrate():
    from backend.database import init_db
    init_db()
    
    conn = sqlite3.connect('/home/pai/pai-hire/ats_phongvan.db')
    cursor = conn.cursor()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if not JDS_DIR.exists():
        print("JDs_Detailed directory not found.")
        return

    migrated = 0
    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat_label = CATEGORY_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " "))
        
        for jd_file in sorted(cat_dir.glob("*.md")):
            # All files, not just Junior_
            job_id = jd_file.stem
            job_title = job_id.replace("Junior_", "").replace("Senior_", "").replace("Mid_", "").replace("Manager_", "").replace("Director_", "").replace("_", " ")
            jd_text = jd_file.read_text(encoding="utf-8")
            
            # Default values
            salary_range = "Thỏa thuận (Cạnh tranh)"
            location = "TP. Hồ Chí Minh (CT Group Tower)"
            work_type = "Toàn thời gian"
            
            cursor.execute("""
                INSERT OR IGNORE INTO jobs (
                    id, title, category, jd_text, salary_range, location, work_type,
                    logo_url, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, job_title, cat_label, jd_text, salary_range, location, work_type,
                None, 1, now, now
            ))
            migrated += 1
            
    conn.commit()
    conn.close()
    print(f"Migrated {migrated} jobs.")

if __name__ == "__main__":
    migrate()
