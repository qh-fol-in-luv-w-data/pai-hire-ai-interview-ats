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
    """Trả danh sách vị trí canonical (chỉ Junior_* — 1 entry/vị trí)."""
    jobs = []
    if not JDS_DIR.exists():
        return jobs
    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat_label = CATEGORY_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " "))
        for jd_file in sorted(cat_dir.glob("Junior_*.md")):
            jobs.append({
                "id":            jd_file.stem,
                "title":         jd_file.stem.replace("_", " "),
                "category":      cat_label,
                "category_slug": cat_dir.name,
            })
    return jobs


def resolve_job_id(job_id: str) -> tuple[str | None, str]:
    """
    Nhận bất kỳ job_id nào (kể cả level-prefixed như Senior_Backend_Developer)
    → trả (canonical_job_id, level). canonical_job_id là id trong get_all_jobs().
    """
    for lv in _JOB_LEVELS:
        if job_id.startswith(lv + "_"):
            base = job_id[len(lv)+1:]
            # Tìm Junior_ file tương ứng
            for cat_dir in JDS_DIR.iterdir():
                if not cat_dir.is_dir():
                    continue
                if (cat_dir / f"Junior_{base}.md").exists():
                    return f"Junior_{base}", lv
            # File Junior không có → thử tìm file level chính xác
            for cat_dir in JDS_DIR.iterdir():
                if not cat_dir.is_dir():
                    continue
                if (cat_dir / f"{job_id}.md").exists():
                    return f"Junior_{base}", lv
    # Không có prefix level → giả sử Junior
    jobs = get_all_jobs()
    matched = next((j for j in jobs if j["id"] == job_id), None)
    return (matched["id"] if matched else None), "Junior"


def get_jd_content(job_id: str) -> str:
    for cat_dir in JDS_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
        f = cat_dir / f"{job_id}.md"
        if f.exists():
            return f.read_text(encoding="utf-8")
    return ""


