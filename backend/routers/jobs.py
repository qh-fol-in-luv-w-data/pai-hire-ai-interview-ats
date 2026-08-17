import os
import uuid
import time
import json
import httpx
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, BackgroundTasks, File, Form, UploadFile, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from backend.database import db, log_application_event
from backend.config import BASE_DIR, ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS

from backend.services.document_service import get_all_jobs, resolve_job_id, get_jd_content
from backend.services.ai_service import _do_score_cv
from backend.security import ALLOWED_CV_EXTENSIONS, MAX_CV_UPLOAD_BYTES, read_upload_limited
from backend.services.auth_service import current_user
router = APIRouter()
_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

@router.get("/jobs")
def list_jobs(category: str = None, q: str = None, location: str = None, work_type: str = None, sort: str = "new", include_inactive: bool = False, x_admin_key: str = Header(None)):
    if include_inactive:
        require_admin(x_admin_key)
    jobs = get_all_jobs(include_inactive=include_inactive)
    if category:
        jobs = [j for j in jobs if j["category_slug"] == category]
    if q:
        needle = q.strip().lower()
        jobs = [j for j in jobs if needle in " ".join([j.get("title", ""), j.get("category", ""), j.get("salary_range", "")]).lower()]
    if location:
        jobs = [j for j in jobs if j.get("location") == location]
    if work_type:
        jobs = [j for j in jobs if j.get("work_type") == work_type]
    if sort == "name":
        jobs.sort(key=lambda job: job.get("title", "").lower())
    categories = sorted({j["category"] for j in jobs})
    return {"total": len(jobs), "categories": categories, "jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, level: str = "Junior", include_inactive: bool = False, x_admin_key: str = Header(None)):
    if include_inactive:
        require_admin(x_admin_key)
    canonical_id, resolved_level = resolve_job_id(job_id, include_inactive=include_inactive)
    jobs = get_all_jobs(include_inactive=include_inactive)
    job = next((j for j in jobs if j["id"] == canonical_id), None) if canonical_id else None
    if not job and jobs:
        job = jobs[0]
        canonical_id = job["id"]
    if not job:
        raise HTTPException(404, "Không tìm thấy vị trí")

    effective_level = level if level in _JOB_LEVELS else resolved_level
    base_pos = canonical_id.replace("Junior_", "")
    base_pos = next((canonical_id[len(prefix)+1:] for prefix in _JOB_LEVELS if canonical_id.startswith(prefix + "_")), base_pos)
    level_job = next((item for item in jobs if item["id"] == f"{effective_level}_{base_pos}"), None)
    if level_job:
        job = level_job
        canonical_id = level_job["id"]
    jd = get_jd_content(f"{effective_level}_{base_pos}") or get_jd_content(canonical_id)
    if not jd:
        jd = f"# MÔ TẢ CÔNG VIỆC: {job['title']}\n\n- Yêu cầu ứng viên theo tiêu chuẩn cấp bậc {effective_level}."

    return {**job, "level": effective_level, "jd_content": jd}


@router.post("/jobs/{job_id}/apply")
async def apply_job(
    job_id:     str,
    background: BackgroundTasks,
    name:       str        = Form(...),
    email:      str        = Form(...),
    phone:      str        = Form(""),
    level:      str        = Form("Junior"),
    cv_file:    UploadFile = File(...),
    request: Request = None,
    authorization: str = Header(None),
    x_candidate_token: str = Header(None),
):
    user = current_user(request, authorization, x_candidate_token, ("candidate", "admin", "platform_admin"))
    account_email = (user["email"] or "").strip().lower()
    if account_email and account_email != (email or "").strip().lower():
        raise HTTPException(400, "Email nộp hồ sơ phải trùng với email tài khoản ứng viên")
    name = user["name"] or name
    email = user["email"] or email
    phone = user["phone"] or phone

    jobs = get_all_jobs()
    # Accept level-prefixed job_id by stripping level prefix for lookup
    LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")
    base_job_id = job_id
    for lv in LEVELS:
        if job_id.startswith(lv + "_"):
            base_job_id = job_id[len(lv)+1:]
            level = lv
            break
    matched = next((j for j in jobs if j["id"] == job_id or j["id"].endswith("_" + base_job_id)), None)
    if not matched:
        raise HTTPException(404, "Không tìm thấy vị trí")
    job_id = matched["id"]  # normalize to existing JD file id

    now    = time.strftime("%Y-%m-%dT%H:%M:%S")
    app_id = "APP-" + uuid.uuid4().hex[:8].upper()

    cv_bytes, ext = await read_upload_limited(
        cv_file,
        allowed_extensions=ALLOWED_CV_EXTENSIONS,
        max_bytes=MAX_CV_UPLOAD_BYTES,
        field_name="CV",
    )
    cv_filename = f"{app_id}{ext}"
    cv_path     = CV_UPLOAD_DIR / cv_filename
    cv_path.write_bytes(cv_bytes)
    from backend.services.document_service import extract_cv_text
    from backend.services.cv_extraction import extract_candidate_info
    cv_info = extract_candidate_info(extract_cv_text(cv_path), name, email, phone)

    # §20 — Phát hiện tái ứng tuyển theo email
    is_reapplicant = False
    prev_app_id    = None
    with db() as conn:
        prev = conn.execute(
            "SELECT id FROM cv_applications WHERE email=? AND job_id=? AND id!=? ORDER BY applied_at DESC LIMIT 1",
            (email, job_id, app_id),
        ).fetchone()
        if prev:
            is_reapplicant = True
            prev_app_id    = prev["id"]
            print(f"[Apply] {app_id} | Tái ứng tuyển — lần trước: {prev_app_id}")

    with db() as conn:
        conn.execute(
            """INSERT INTO cv_applications
               (id, job_id, name, email, phone, cv_filename, cv_path, applied_at, is_reapplicant, prev_app_id, level, cv_extracted_info)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (app_id, job_id, name, email, phone, cv_filename,
             str(cv_path.relative_to(BASE_DIR)), now, is_reapplicant, prev_app_id, level, json.dumps(cv_info, ensure_ascii=False)),
        )
    log_application_event(
        app_id,
        email,
        "application_submitted",
        f"Ứng viên nộp hồ sơ cho vị trí {job_id}.",
        {"job_id": job_id, "level": level, "is_reapplicant": is_reapplicant, "prev_app_id": prev_app_id},
    )

    background.add_task(_do_score_cv, app_id, cv_path, job_id, level)
    print(f"[Apply] {app_id} | {name} | {job_id}")

    return {
        "ok": True, "application_id": app_id,
        "is_reapplicant": is_reapplicant,
        "message": "CV đã nhận, đang chấm điểm tự động...",
    }

from backend.config import JDS_DIR, require_admin

@router.post("/jobs/upload-jd-file")
async def upload_jd_file(
    file: UploadFile = File(...),
    x_admin_key: str = Header(None)
):
    require_admin(x_admin_key)
    from backend.services.document_service import extract_cv_text

    import tempfile
    import shutil
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        text = extract_cv_text(tmp_path)
    finally:
        tmp_path.unlink()

    return {"text": text}

from pydantic import BaseModel

class SaveJDReq(BaseModel):
    id: str = None
    category: str
    title: str
    jd_content: str
    salary_range: str = "Thỏa thuận (Cạnh tranh)"
    location: str = "TP. Hồ Chí Minh (CT Group Tower)"
    work_type: str = "Toàn thời gian"
    logo_url: str = None
    part1_limit: int = 11
    part2_limit: int = 7
    part3_limit: int = 5
    is_active: bool = True

class JobActivationReq(BaseModel):
    is_active: bool

@router.patch("/jobs/{job_id}/active")
def set_job_active(job_id: str, req: JobActivationReq, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        existing = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Không tìm thấy vị trí tuyển dụng")
        conn.execute("UPDATE jobs SET is_active=?, updated_at=? WHERE id=?", (
            int(req.is_active), time.strftime("%Y-%m-%dT%H:%M:%S"), job_id,
        ))
    return {"success": True, "id": job_id, "is_active": req.is_active}

@router.post("/jobs/save-jd")
def save_jd(req: SaveJDReq, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    category = req.category.strip()
    title = req.title.strip()
    content = req.jd_content.strip()

    if not category or not title or not content:
        raise HTTPException(400, "Vui lòng nhập đầy đủ Danh mục, Tên vị trí và Nội dung JD")

    job_id = req.id.strip() if req.id and req.id.strip() else title.replace(" ", "_")
    salary_range = req.salary_range
    if not salary_range or salary_range == "AUTO" or salary_range.startswith("Thỏa thuận"):
        from backend.services.salary_benchmarks import market_salary
        salary_range = market_salary(job_id, title, category)

    from backend.database import db
    import time
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    with db() as conn:
        existing = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE jobs SET title=?, category=?, jd_text=?, salary_range=?, location=?,
                                work_type=?, logo_url=?, part1_limit=?, part2_limit=?, part3_limit=?, is_active=?, updated_at=?
                WHERE id=?
            """, (title, category, content, salary_range, req.location, req.work_type, req.logo_url,
                  req.part1_limit, req.part2_limit, req.part3_limit, int(req.is_active), now, job_id))
        else:
            conn.execute("""
                INSERT INTO jobs (id, title, category, jd_text, salary_range, location, work_type, logo_url, part1_limit, part2_limit, part3_limit, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, title, category, content, salary_range, req.location, req.work_type, req.logo_url,
                  req.part1_limit, req.part2_limit, req.part3_limit, int(req.is_active), now, now))

    return {
        "success": True,
        "message": "Đã lưu và cập nhật JD thành công!",
        "id": job_id,
        "category": category,
        "salary_range": salary_range,
        "is_active": req.is_active,
    }
