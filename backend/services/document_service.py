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


def get_all_jobs():
    """Trả danh sách vị trí canonical kèm metadata phong phú cho giao diện VietnamWorks."""
    jobs = []
    if not JDS_DIR.exists():
        return jobs
    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat_label = CATEGORY_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " "))
        for jd_file in sorted(cat_dir.glob("Junior_*.md")):
            job_title = jd_file.stem.replace("_", " ")
            jobs.append({
                "id":            jd_file.stem,
                "title":         job_title,
                "category":      cat_label,
                "category_slug": cat_dir.name,
                "salary_range":  "Thỏa thuận (Cạnh tranh)",
                "location":      "TP. Hồ Chí Minh (CT Group Tower)",
                "work_type":     "Toàn thời gian",
                "hot_badge":     True,
                "ai_match_rate": "95%",
                "tags":          ["AI Interview", "Đào tạo AI", "Phỏng vấn Online"]
            })
    return jobs


def resolve_job_id(job_id: str) -> tuple[str | None, str]:
    """
    Nhận bất kỳ job_id nào → trả (canonical_job_id, level).
    """
    if not job_id:
        return None, "Junior"

    jobs = get_all_jobs()
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
    if not JDS_DIR.exists():
        return ""
    # Search exact match
    for cat_dir in JDS_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
        for f in cat_dir.glob("*.md"):
            if f.stem == job_id or f.stem.lower() == job_id.lower():
                return f.read_text(encoding="utf-8", errors="ignore")

    # Try fuzzy match without level prefix
    for lv in _JOB_LEVELS:
        if job_id.startswith(lv + "_"):
            base = job_id[len(lv)+1:]
            for cat_dir in JDS_DIR.iterdir():
                if not cat_dir.is_dir():
                    continue
                for f in cat_dir.glob("*.md"):
                    if f.stem.endswith("_" + base):
                        return f.read_text(encoding="utf-8", errors="ignore")
    return ""


