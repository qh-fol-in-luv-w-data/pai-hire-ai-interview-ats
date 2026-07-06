import os
import uuid
import time
import json
import httpx
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, BackgroundTasks, File, Form, UploadFile, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from backend.database import db
from backend.config import BASE_DIR, ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTION_META, CATEGORY_LABELS

from backend.services.document_service import get_all_jobs, resolve_job_id, get_jd_content
from backend.services.ai_service import _do_score_cv
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
    if not canonical_id:
        raise HTTPException(404, "Không tìm thấy vị trí")
    jobs = get_all_jobs()
    job  = next((j for j in jobs if j["id"] == canonical_id), None)
    if not job:
        raise HTTPException(404, "Không tìm thấy vị trí")
    # Lấy level từ query param nếu có, fallback về level resolve từ job_id
    effective_level = level if level in _JOB_LEVELS else resolved_level
    base_pos = canonical_id.replace("Junior_", "")
    jd = get_jd_content(f"{effective_level}_{base_pos}") or get_jd_content(canonical_id)
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
):
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

    ext         = Path(cv_file.filename).suffix or ".pdf"
    cv_filename = f"{app_id}{ext}"
    cv_path     = CV_UPLOAD_DIR / cv_filename
    cv_path.write_bytes(await cv_file.read())

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

    background.add_task(_do_score_cv, app_id, cv_path, job_id, level)
    print(f"[Apply] {app_id} | {name} | {job_id}")

    return {
        "ok": True, "application_id": app_id,
        "is_reapplicant": is_reapplicant,
        "message": "CV đã nhận, đang chấm điểm tự động...",
    }


