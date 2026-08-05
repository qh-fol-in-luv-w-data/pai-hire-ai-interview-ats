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
router = APIRouter()
_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

@router.get("/jobs")
def list_jobs(category: str = None):
    jobs = get_all_jobs()
    if category:
        jobs = [j for j in jobs if j["category_slug"] == category]
    categories = sorted({j["category"] for j in jobs})
    return {"total": len(jobs), "categories": categories, "jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, level: str = "Junior"):
    canonical_id, resolved_level = resolve_job_id(job_id)
    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == canonical_id), None) if canonical_id else None
    if not job and jobs:
        job = jobs[0]
        canonical_id = job["id"]
    if not job:
        raise HTTPException(404, "Không tìm thấy vị trí")

    effective_level = level if level in _JOB_LEVELS else resolved_level
    base_pos = canonical_id.replace("Junior_", "")
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
    x_candidate_token: str = Header(None),
):
    if not x_candidate_token:
        raise HTTPException(401, "Vui lòng đăng nhập hoặc đăng ký tài khoản ứng viên trước khi nộp CV")
    with db() as conn:
        user = conn.execute(
            "SELECT id, name, email, phone FROM users WHERE id=? AND role IN ('candidate', 'admin')",
            (x_candidate_token,),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Phiên đăng nhập ứng viên không hợp lệ, vui lòng đăng nhập lại")
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
               (id, job_id, name, email, phone, cv_filename, cv_path, applied_at, is_reapplicant, prev_app_id, level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (app_id, job_id, name, email, phone, cv_filename,
             str(cv_path.relative_to(BASE_DIR)), now, is_reapplicant, prev_app_id, level),
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

from pydantic import BaseModel
from backend.config import JDS_DIR, require_admin

class SaveJDReq(BaseModel):
    category: str
    title: str
    jd_content: str

@router.post("/jobs/save-jd")
def save_jd(req: SaveJDReq, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    category = req.category.strip()
    title = req.title.strip().replace(" ", "_")
    content = req.jd_content.strip()

    if not category or not title or not content:
        raise HTTPException(400, "Vui lòng nhập đầy đủ Danh mục, Tên vị trí và Nội dung JD")

    cat_dir = JDS_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{title}_JD.md" if not title.endswith("_JD.md") else title
    jd_file_path = cat_dir / file_name
    jd_file_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "message": "Đã lưu và cập nhật JD thành công!",
        "file": file_name,
        "category": category
    }
