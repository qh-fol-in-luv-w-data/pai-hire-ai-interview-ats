import sqlite3
import time
from pathlib import Path

CATEGORY_LABELS = {
    "Công_Nghệ_Thông_Tin_(IT)": "Công Nghệ Thông Tin (IT)",
    "Kinh_Doanh_&_Bán_Hàng_(Sales_&_Business_Development)": "Kinh Doanh & Bán Hàng",
    "Chuỗi_Cung_Ứng_&_Logistics_(Supply_Chain)": "Chuỗi Cung Ứng & Logistics",
    "Kỹ_Thuật_&_Sản_Xuất_(Engineering_&_Manufacturing)": "Kỹ Thuật & Sản Xuất",
    "Marketing_&_Truyền_Thông_(Marketing_&_PR)": "Marketing & Truyền Thông",
    "Nhân_Sự_&_Hành_Chính_(HR_&_Admin)": "Nhân Sự & Hành Chính",
    "Thiết_Kế_&_Sáng_Tạo_(Design_&_Creative)": "Thiết Kế & Sáng Tạo",
    "Tài_Chính_&_Kế_Toán_(Finance_&_Accounting)": "Tài Chính & Kế Toán"
}

conn = sqlite3.connect('/home/pai/pai-hire/ats_phongvan.db')
cursor = conn.cursor()
now = time.strftime("%Y-%m-%dT%H:%M:%S")

jds_dir = Path("/home/pai/pai-hire/JDs_Detailed")
migrated = 0

if jds_dir.exists():
    for cat_dir in sorted(jds_dir.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat_label = CATEGORY_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " "))
        
        for jd_file in sorted(cat_dir.glob("*.md")):
            job_id = jd_file.stem
            job_title = job_id.replace("Junior_", "").replace("Senior_", "").replace("Mid_", "").replace("Manager_", "").replace("Director_", "").replace("_", " ")
            jd_text = jd_file.read_text(encoding="utf-8")
            
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
