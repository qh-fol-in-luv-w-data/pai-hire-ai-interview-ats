import os
import re
from pathlib import Path
from backend.config import JDS_DIR, CATEGORY_LABELS

_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

def extract_cv_text(cv_path: Path) -> str:
    if cv_path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(cv_path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            pass
        try:
            import pdfplumber
            with pdfplumber.open(cv_path) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            pass
        import subprocess
        r = subprocess.run(["pdftotext", str(cv_path), "-"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
    elif cv_path.suffix.lower() in (".docx",):
        try:
            import docx
            doc = docx.Document(str(cv_path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            pass
    try:
        return cv_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "[Không thể đọc CV]"


def get_all_jobs(include_inactive: bool = False):
    from backend.database import db
    jobs = []
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs" if include_inactive else "SELECT * FROM jobs WHERE is_active=1"
        ).fetchall()
        for r in rows:
            jobs.append({
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "category_slug": r["category"].replace(" ", "_"),
                "salary_range": r["salary_range"] or "Thỏa thuận (Cạnh tranh)",
                "location": r["location"] or "TP. Hồ Chí Minh (CT Group Tower)",
                "work_type": r["work_type"] or "Toàn thời gian",
                "logo_url": r["logo_url"],
                "is_active": bool(r["is_active"]),
                "hot_badge": True,
                "ai_match_rate": "95%",
                "tags": ["AI Interview", "Phỏng vấn Online"],
                "part1_limit": r["part1_limit"],
                "part2_limit": r["part2_limit"],
                "part3_limit": r["part3_limit"]
            })
    return jobs


def resolve_job_id(job_id: str, include_inactive: bool = False) -> tuple[str | None, str]:
    """
    Nhận bất kỳ job_id nào → trả (canonical_job_id, level).
    """
    if not job_id:
        return None, "Junior"

    jobs = get_all_jobs(include_inactive=include_inactive)
    # 1. Direct match with any canonical job id
    matched = next((j for j in jobs if j["id"] == job_id), None)
    if matched:
        for lv in _JOB_LEVELS:
            if job_id.startswith(lv + "_"):
                return matched["id"], lv
        return matched["id"], "Junior"

    # 2. Match after removing level prefix
    for lv in _JOB_LEVELS:
        if job_id.startswith(lv + "_"):
            base = job_id[len(lv)+1:]
            matched = next((j for j in jobs if j["id"].endswith("_" + base) or j["id"] == f"Junior_{base}"), None)
            if matched:
                return matched["id"], lv

    # 3. Fallback: match by title / stem
    clean_id = job_id.lower().replace(" ", "_")
    matched = next((j for j in jobs if j["id"].lower() == clean_id or j["id"].lower().replace("junior_", "") in clean_id), None)
    if matched:
        return matched["id"], "Junior"

    # If jobs exist, fallback to first job
    if jobs:
        return jobs[0]["id"], "Junior"

    return None, "Junior"


def get_jd_content(job_id: str) -> str:
    from backend.database import db
    with db() as conn:
        row = conn.execute("SELECT jd_text FROM jobs WHERE id=? OR id=?", (job_id, job_id.lower())).fetchone()
        if row:
            return row["jd_text"]
        
        # Fuzzy match
        for lv in _JOB_LEVELS:
            if job_id.startswith(lv + "_"):
                base = job_id[len(lv)+1:]
                row = conn.execute("SELECT jd_text FROM jobs WHERE id LIKE ?", ('%_' + base,)).fetchone()
                if row:
                    return row["jd_text"]
    return ""

