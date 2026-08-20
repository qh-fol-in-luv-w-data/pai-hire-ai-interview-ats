"""
PAI HR — External API v1
========================
Auth: Header Authorization: Bearer <company_api_key>
      Tương thích cũ: Authorization: token <user_id>:<api_key>

Endpoints:
  POST /api/v1/score-cv             — Chấm điểm CV theo JD text, sinh câu hỏi
  POST /api/v1/schedule             — Tạo link phỏng vấn giới hạn theo khung giờ
  GET  /api/v1/report/{app_id}      — Báo cáo kết quả theo mã ứng viên
  GET  /api/v1/slot/{token}/validate — Kiểm tra token lịch hẹn (dùng nội bộ)
"""

import os
import re
import json
import uuid
import time
import hashlib
from hmac import compare_digest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.database import db, log_application_event
from backend.config import (
    BASE_DIR,
    CV_UPLOAD_DIR,
    INTERVIEW_URL,
    OPENAI_API_KEY,
    SCORE_PROMPT,
    PASS_SCORE,
)
from backend.security import (
    ALLOWED_CV_EXTENSIONS,
    MAX_CV_UPLOAD_BYTES,
    bounded_text,
    read_upload_limited,
)
from backend.services.ai_service import normalize_cv_score

router = APIRouter(prefix="/api/v1", tags=["External API v1"])
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_slot_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt

# ─────────────────────────────────────────────────────────────
# Auth — Bearer token lưu trong settings (key='api_token')
# Admin set qua POST /admin/settings {"api_token": "..."}
# Gọi API: Authorization: Bearer <token>
# Fallback: env API_TOKEN nếu chưa set
# ─────────────────────────────────────────────────────────────
def _get_valid_token() -> str:
    """Lấy token hợp lệ từ settings DB hoặc env API_TOKEN."""
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='api_token'").fetchone()
        if row and row["value"]:
            return row["value"]
    token = os.environ.get("API_TOKEN", "")
    if not token:
        # Không trả 500 khi client gửi một key cũ mà server chưa cấu hình lại.
        # 503 cho biết đây là lỗi cấu hình máy chủ, không phải lỗi request của client.
        raise HTTPException(503, "Legacy API key chưa được cấu hình trên server")
    return token


def _authorization_token(authorization: str | None) -> str:
    """Đọc Bearer mới và format `token user_id:api_key` của API cũ."""
    if not authorization:
        raise HTTPException(401, "Thiếu Authorization header")
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2:
        raise HTTPException(401, "Authorization phải có dạng: Bearer <token>")
    scheme, credential = parts[0].lower(), parts[1].strip()
    if scheme == "bearer" and credential:
        return credential
    if scheme == "token" and credential:
        # API cũ dùng `token <user_id>:<api_key>`. user_id không dùng để
        # phân quyền nên chỉ giữ phần key sau dấu ':' cuối cùng.
        return credential.rsplit(":", 1)[-1].strip()
    raise HTTPException(401, "Authorization phải có dạng: Bearer <token>")


def _require_tenant(authorization: str = Header(None)) -> dict:
    token = _authorization_token(authorization)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        row = conn.execute("""
            SELECT c.id AS company_id, c.slug AS company_slug, c.name AS company_name, k.id AS api_key_id, k.scopes, k.expires_at
            FROM company_api_keys k JOIN companies c ON c.id=k.company_id
            WHERE k.key_hash=? AND k.is_active=1 AND c.is_active=1
        """, (token_hash,)).fetchone()
        if row:
            if row["expires_at"] and row["expires_at"] < time.strftime("%Y-%m-%dT%H:%M:%S"):
                raise HTTPException(401, "API key đã hết hạn")
            conn.execute("UPDATE company_api_keys SET last_used_at=? WHERE key_hash=?", (time.strftime("%Y-%m-%dT%H:%M:%S"), token_hash))
            return dict(row)
    # Tương thích khóa API cũ: chỉ nhìn thấy tenant PAI Internal, không thể thấy tenant khác.
    if compare_digest(token, _get_valid_token()):
        return {"company_id": "company_default", "company_slug": "pai-internal", "company_name": "PAI Internal", "api_key_id": None, "scopes": "*"}
    raise HTTPException(401, "API key không hợp lệ hoặc đã bị thu hồi")


# ─────────────────────────────────────────────────────────────
# Cache helper (dùng khi use_cache=TRUE)
# ─────────────────────────────────────────────────────────────
_SCORE_CACHE: dict = {}   # key: md5(cv_bytes + jd_text) -> result dict

def _cache_key(cv_bytes: bytes, jd_text: str, mode: str) -> str:
    h = hashlib.md5(cv_bytes + jd_text.encode() + mode.encode()).hexdigest()
    return h


# ─────────────────────────────────────────────────────────────
# 1. POST /api/v1/score-cv
#    Nhận CV file + JD text → chấm điểm + sinh câu hỏi
# ─────────────────────────────────────────────────────────────
@router.get("/applications/{app_id}/basic")
def get_application_basic(app_id: str, authorization: str = Header(None), x_interview_session: str = Header(None)):
    # Interview page has no company API key; it proves the capability minted
    # after validating the unguessable slot instead.
    if x_interview_session:
        from backend.services.interview_access import require_access
        require_access(app_id, x_interview_session)
        tenant = None
    else:
        tenant = _require_tenant(authorization)
    with db() as conn:
        row = conn.execute("SELECT name, email, job_id, level FROM cv_applications WHERE id=?" + (" AND company_id=?" if tenant else ""), (app_id, tenant["company_id"]) if tenant else (app_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ ứng viên")

    job_title = row["job_id"]
    try:
        from backend.services.document_service import get_all_jobs
        jobs = get_all_jobs()
        job = next((j for j in jobs if j["id"] == row["job_id"]), None)
        if job:
            job_title = job.get("title") or job_title
    except Exception:
        pass

    return {
        "name": row["name"],
        "email": row["email"],
        "job_id": row["job_id"],
        "level": row["level"],
        "job_title": job_title,
    }


@router.post("/score-cv")
async def api_score_cv(
    cv_file: UploadFile = File(..., description="File CV (PDF/DOCX)"),
    jd_text: str = Form(..., description="Nội dung mô tả công việc (JD) dạng text thuần"),
    mode: str = Form("candidate", description="'candidate' (ứng viên) hoặc 'employee' (nhân viên nội bộ)"),
    use_cache: str = Form("FALSE", description="'TRUE' để dùng cache, tránh gọi AI lặp lại"),
    level: str = Form("Junior", description="Cấp bậc: Entry/Junior/Mid/Senior/Manager/Director"),
    candidate_name: str = Form("", description="Tên ứng viên (tuỳ chọn)"),
    candidate_email: str = Form("", description="Email ứng viên (tuỳ chọn)"),
    candidate_id: str = Form(None, description="ID định danh ứng viên (để cộng điểm update)"),
    skip_scoring: bool = Form(False, description="Bỏ qua chấm điểm (chỉ sinh câu hỏi và tạo app)"),
    authorization: str = Header(None),
    idempotency_key: str = Header(None),
):
    """
    **Chấm điểm CV theo JD text và sinh câu hỏi phỏng vấn.**

    - Nhận file CV (PDF/DOCX) và nội dung JD dạng text tự do
    - Hỗ trợ `mode=employee` để điều chỉnh prompt phù hợp đánh giá nội bộ
    - Bật `use_cache=TRUE` để tái dùng kết quả nếu cùng CV + JD đã từng chấm

    **Auth:** `Authorization: Bearer <api_key>`
    (Tương thích cũ: `Authorization: token <user_id>:<api_key>`)
    """
    tenant = _require_tenant(authorization)

    # Không cho phép tạo hồ sơ API với điểm mặc định 10/10. Mọi CV gửi qua
    # API đều phải đi qua chấm điểm thật trước khi được cấp link phỏng vấn.
    skip_scoring = False

    if not OPENAI_API_KEY:
        raise HTTPException(503, "OpenAI chưa được cấu hình trên server")

    jd_text = bounded_text(jd_text, "jd_text")
    cv_bytes, ext = await read_upload_limited(
        cv_file,
        allowed_extensions=ALLOWED_CV_EXTENSIONS,
        max_bytes=MAX_CV_UPLOAD_BYTES,
        field_name="CV",
    )

    # --- Cache check ---
    use_cache_flag = use_cache.strip().upper() == "TRUE"
    ck = _cache_key(cv_bytes, jd_text, mode) + f"_tenant_{tenant['company_id']}_skip_{skip_scoring}"
    if use_cache_flag and ck in _SCORE_CACHE:
        cached = _SCORE_CACHE[ck]
        return JSONResponse({**cached, "cached": True})
    from backend.services.quota_service import consume
    consume(tenant["company_id"], tenant.get("api_key_id"), bucket="cv", endpoint="score-cv", request_key=idempotency_key)

    # --- Lưu file CV tạm để extract text ---
    app_id = "APP-" + uuid.uuid4().hex[:8].upper()
    cv_dir = CV_UPLOAD_DIR / app_id
    cv_dir.mkdir(parents=True, exist_ok=True)
    cv_path = cv_dir / f"cv{ext}"
    cv_path.write_bytes(cv_bytes)

    # --- Trích xuất text CV ---
    from backend.services.document_service import extract_cv_text
    cv_text = extract_cv_text(cv_path)
    if not cv_text.strip():
        raise HTTPException(422, "Không thể đọc nội dung CV. Hãy dùng file PDF/DOCX chuẩn.")
    from backend.services.cv_extraction import extract_candidate_info
    cv_info = extract_candidate_info(cv_text, candidate_name, candidate_email)

    # --- Lấy pass score từ settings ---
    pass_score = PASS_SCORE
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='cv_pass_score'").fetchone()
        if row and row["value"]:
            try:
                pass_score = float(row["value"])
                if pass_score > 5:
                    pass_score = pass_score / 2
            except Exception:
                pass

    # --- Prompt điều chỉnh theo mode ---
    mode_note = ""
    if mode.lower() == "employee":
        mode_note = (
            "\n[CHÚ Ý: Đây là đánh giá nhân viên nội bộ. "
            "Tập trung vào mức độ phù hợp với vị trí mới / thăng chức, "
            "ưu tiên thành tích thực tế hơn bằng cấp.]\n"
        )

    jd_full = mode_note + jd_text.strip()

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # --- Chấm điểm ---
    if skip_scoring:
        score_result = {
            "criteria_scores": {"Mặc định": 10.0},
            "reasons": {"Mặc định": "Bypass scoring (chỉ tạo lịch)"},
            "summary": "CV được gửi trực tiếp để tạo lịch phỏng vấn."
        }
        total = 10.0
        verdict = "pass"
        c = score_result["criteria_scores"]
    else:
        try:
            prompt = SCORE_PROMPT.format(
                jd=jd_full[:4000],
                cv=cv_text[:5000],
                pass_score=pass_score,
            )
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2200,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            score_result = json.loads(raw)
        except Exception as e:
            raise HTTPException(502, f"Lỗi AI chấm điểm: {e}")

        score_result, total = normalize_cv_score(score_result)
        c = score_result.get("criteria_scores", {})
        verdict = "pass" if total >= pass_score else "fail"

    # --- Sinh câu hỏi chuyên sâu ---
    # Dùng JD text hash làm job_id tạm thời, đồng thời làm khoá cache năng lực JD
    # (khung năng lực trích một lần cho mỗi nội dung JD, không phụ thuộc ứng viên).
    jd_slug = "jd_" + hashlib.md5(jd_text.encode()).hexdigest()[:8]
    deep_questions = []
    deep_coverage = None
    bonus_applied = False
    bonus_reason = ""
    bonus_points = 0.0

    old_hist = None
    if candidate_id and not skip_scoring:
        with db() as conn:
            old_hist = conn.execute("SELECT * FROM cv_score_history WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1", (candidate_id,)).fetchone()
            
    if old_hist:
        # Nộp lại -> Gọi AI kiểm tra update
        try:
            from backend.config import CV_UPDATE_CHECK_PROMPT
            check_prompt = CV_UPDATE_CHECK_PROMPT.format(
                old_cv=old_hist["cv_text"][:5000], 
                deep_questions=old_hist["deep_questions"], 
                new_cv=cv_text[:5000]
            )
            chk_resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": check_prompt}],
                temperature=0.1,
                max_tokens=800,
            )
            chk_raw = chk_resp.choices[0].message.content.strip()
            chk_raw = re.sub(r"^```(?:json)?\s*", "", chk_raw)
            chk_raw = re.sub(r"\s*```$", "", chk_raw)
            chk_data = json.loads(chk_raw)
            bonus_reason = chk_data.get("reason", "Ứng viên không bổ sung thông tin trả lời các câu hỏi trước đó.")
            if chk_data.get("addressed_questions"):
                update_score = float(chk_data.get("score", 0))
                bonus = min(update_score * 0.5, 0.5) # Max 0.5
                if bonus > 0:
                    total += bonus
                    total = min(total, 5.0)
                    total = round(total, 2)
                    bonus_applied = True
                    bonus_points = bonus
        except Exception as e:
            print(f"[API v1] Cross check error: {e}")
        # Không sinh câu hỏi mới cho ứng viên nộp lại
        deep_questions = []
    else:
        # Lần đầu -> Sinh câu hỏi chuyên sâu, ràng buộc theo năng lực cốt lõi của JD
        try:
            from backend.services.ai_service import generate_deep_questions
            deep_result = await generate_deep_questions(
                cv_text, jd_text, job_id=jd_slug, level=level,
            )
            deep_questions = deep_result["questions"]
            deep_coverage = deep_result["coverage"]
        except Exception as e:
            print(f"[API v1] Deep questions error: {e}")

    # --- Lưu vào DB ---
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    # --- Lưu lịch sử để cộng điểm lần sau ---
    if candidate_id:
        with db() as conn:
            conn.execute(
                "INSERT INTO cv_score_history (id, candidate_id, cv_text, score, deep_questions, created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), candidate_id, cv_text, total, json.dumps(deep_questions, ensure_ascii=False), now)
            )

    score_breakdown = {
        **score_result,
        "deep_questions": deep_questions,
        "deep_questions_coverage": deep_coverage,
        "bonus_applied": bonus_applied,
        "bonus_points": bonus_points,
        "bonus_reason": bonus_reason
    }
    with db() as conn:
        conn.execute(
            """INSERT INTO cv_applications
               (id, job_id, name, email, phone, cv_filename, cv_path,
               cv_score, score_breakdown, ai_summary, status, applied_at, level, cv_extracted_info, application_source, company_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                app_id, jd_slug,
                cv_info.get("name") or candidate_name or candidate_id or f"Candidate {app_id[-4:]}",
                cv_info.get("email") or candidate_email or f"{app_id.lower()}@api.local",
                cv_info.get("phone"),
                cv_file.filename or "cv.pdf",
                str(cv_path.relative_to(BASE_DIR)),
                total,
                json.dumps(score_breakdown, ensure_ascii=False),
                score_result.get("summary", ""),
                f"waiting_for_reply_{'passed' if verdict == 'pass' else 'failed'}",
                now,
                level,
                json.dumps(cv_info, ensure_ascii=False),
                "api",
                tenant["company_id"],
            ),
        )
    app_email = cv_info.get("email") or candidate_email or f"{app_id.lower()}@api.local"
    log_application_event(
        app_id,
        app_email,
        "application_scored_api",
        f"API đã nhận và đánh giá hồ sơ: {round(total, 2)}/5.",
        {"job_id": jd_slug, "level": level, "verdict": verdict, "mode": mode, "company_id": tenant["company_id"]},
    )

    try:
        app_out_id = int(candidate_id) if candidate_id and candidate_id.isdigit() else (candidate_id or app_id)
    except Exception:
        app_out_id = candidate_id or app_id

    result = {
        "applicant_id": app_out_id,
        "score": total,
        "feedback": score_result.get("summary", ""),
        "criteria_scores": c,
        "questions_id": deep_questions,
        "bonus_applied": bonus_applied,
        "bonus_points": bonus_points,
        "bonus_reason": bonus_reason,
        
        # Original fields kept for internal logic
        "app_id": app_id,
        "verdict": verdict,
        "pass_threshold": pass_score,
        "mode": mode,
        "reasons": score_result.get("reasons", {}),
        "summary": score_result.get("summary", ""),
        "deep_questions": deep_questions,
        "cached": False,
    }

    # Lưu cache
    if use_cache_flag:
        _SCORE_CACHE[ck] = result

    return JSONResponse(result)


# ─────────────────────────────────────────────────────────────
# 2. POST /api/v1/schedule
#    Đặt lịch + tạo link phỏng vấn giới hạn theo khung giờ
# ─────────────────────────────────────────────────────────────
class ScheduleRequest(BaseModel):
    app_id: str
    start_time: str   # ISO 8601, vd: "2025-08-01T09:00:00+07:00"
    end_time: str     # ISO 8601
    position_id: str = ""
    level: str = "Junior"


@router.post("/schedule")
async def api_schedule_interview(
    body: ScheduleRequest,
    authorization: str = Header(None),
    idempotency_key: str = Header(None),
):
    """
    **Tạo link phỏng vấn giới hạn theo khung giờ.**

    Ứng viên chỉ vào được trong khoảng `start_time` → `end_time`.

    **Auth:** `Authorization: Bearer <api_key>`
    (Tương thích cũ: `Authorization: token <user_id>:<api_key>`)
    """
    tenant = _require_tenant(authorization)
    from backend.services.quota_service import consume
    if not consume(tenant["company_id"], tenant.get("api_key_id"), bucket="interview", endpoint="schedule", request_key=idempotency_key):
        raise HTTPException(409, "Yêu cầu trùng đã được xử lý; dùng app_id mới hoặc Idempotency-Key mới")

    with db() as conn:
        app = conn.execute(
            "SELECT * FROM cv_applications WHERE id=? AND company_id=?", (body.app_id, tenant["company_id"])
        ).fetchone()
    if not app:
        raise HTTPException(404, f"Không tìm thấy app_id='{body.app_id}'")

    position_id = body.position_id or app["job_id"]
    level = body.level or app["level"] or "Junior"

    try:
        start_dt = parse_slot_datetime(body.start_time)
        end_dt   = parse_slot_datetime(body.end_time)
    except ValueError as e:
        raise HTTPException(422, f"Định dạng thời gian không hợp lệ: {e}")

    if end_dt <= start_dt:
        raise HTTPException(422, "end_time phải sau start_time")

    token = uuid.uuid4().hex
    now_str = time.strftime("%Y-%m-%dT%H:%M:%S")

    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_slots (
                token       TEXT PRIMARY KEY,
                app_id      TEXT NOT NULL,
                position_id TEXT NOT NULL,
                level       TEXT NOT NULL DEFAULT 'Junior',
                start_time  TEXT NOT NULL,
                end_time    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                used        INTEGER DEFAULT 0,
                company_id TEXT
            )
        """)
        conn.execute(
            """INSERT INTO interview_slots
               (token, app_id, position_id, level, start_time, end_time, created_at, company_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (token, body.app_id, position_id, level,
             start_dt.isoformat(), end_dt.isoformat(), now_str, tenant["company_id"]),
        )

    base = INTERVIEW_URL.rsplit("/interview", 1)[0]
    interview_link = f"{base}/interview?slot={token}"

    # API tạo lịch phải phản ánh ngay trên hồ sơ: đã cấp link phỏng vấn.
    with db() as conn:
        app_status = conn.execute("SELECT email FROM cv_applications WHERE id=? AND company_id=?", (body.app_id, tenant["company_id"])).fetchone()
        conn.execute(
            """UPDATE cv_applications
               SET status='interview_link_sent', interview_link=?, interview_slot_token=?, interview_link_sent_at=?, interview_link_source='api',
                   cv_score=NULL, score_breakdown=NULL, ai_summary=NULL
               WHERE id=? AND company_id=?""",
            (interview_link, token, now_str, body.app_id, tenant["company_id"]),
        )
        # API chỉ cần CV đến thời điểm cấp link; thông tin đã trích xuất vẫn giữ trong DB.
        api_cv = conn.execute("SELECT cv_path FROM cv_applications WHERE id=? AND company_id=? AND application_source='api'", (body.app_id, tenant["company_id"])).fetchone()
        if api_cv and api_cv["cv_path"]:
            try:
                cv_file_path = BASE_DIR / api_cv["cv_path"]
                if cv_file_path.is_file():
                    os.unlink(cv_file_path)
            except Exception:
                pass
            conn.execute("UPDATE cv_applications SET cv_path=NULL WHERE id=? AND company_id=?", (body.app_id, tenant["company_id"]))
    log_application_event(
        body.app_id,
        app_status["email"] if app_status else "",
        "interview_link_sent",
        "API đã tạo và cấp link phỏng vấn cho ứng viên.",
        {"interview_url": interview_link, "slot_token": token, "start_time": start_dt.isoformat(), "end_time": end_dt.isoformat()},
    )

    return JSONResponse({
        "token": token,
        "app_id": body.app_id,
        "interview_url": interview_link,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "note": "Ứng viên chỉ được truy cập link trong khung giờ đã đặt.",
    })


# ─────────────────────────────────────────────────────────────
# 2b. POST /api/v1/schedule-with-cv
#     Nhận CV + JD + lịch trong một request.
#     Nếu truyền app_id đã có thì bỏ qua bước chấm CV.
# ─────────────────────────────────────────────────────────────
@router.post("/schedule-with-cv")
async def api_schedule_with_cv(
    start_time: str = Form(...),
    end_time: str = Form(...),
    cv_file: UploadFile = File(None),
    jd_text: str = Form(""),
    app_id: str = Form(""),
    position_id: str = Form(""),
    level: str = Form("Junior"),
    mode: str = Form("candidate"),
    use_cache: str = Form("TRUE"),
    candidate_name: str = Form(""),
    candidate_email: str = Form(""),
    candidate_id: str = Form(None),
    part1_limit: int = Form(11, description="Số câu hỏi phần 1 (mặc định)"),
    part2_limit: int = Form(7, description="Số câu hỏi phần 2 (sinh từ CV)"),
    part3_limit: int = Form(5, description="Số câu hỏi phần 3 (đào sâu)"),
    authorization: str = Header(None),
    idempotency_key: str | None = Header(None),
):
    """
    Tạo lịch phỏng vấn trong một request.

    - Request mới: gửi `cv_file` + `jd_text`, hệ thống chấm CV rồi tạo lịch.
    - Hồ sơ đã qua vòng lọc CV: chỉ gửi `app_id`, hệ thống không chấm lại.
    - Hệ thống sẽ tự động cấu hình và sinh bộ câu hỏi dựa trên các tham số `part1_limit`, `part2_limit`, `part3_limit`.
    """
    tenant = _require_tenant(authorization)

    # Validate lịch trước khi chấm CV/tạo audio để request sai không để lại hồ sơ dở.
    try:
        slot_start = parse_slot_datetime(start_time)
        slot_end = parse_slot_datetime(end_time)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"Định dạng thời gian không hợp lệ: {exc}")
    if slot_end <= slot_start:
        raise HTTPException(422, "end_time phải sau start_time")

    score_data = None
    if app_id.strip():
        with db() as conn:
            if not conn.execute("SELECT 1 FROM cv_applications WHERE id=? AND company_id=?", (app_id.strip(), tenant["company_id"])).fetchone():
                raise HTTPException(404, f"Không tìm thấy app_id='{app_id.strip()}'")
        app_id = app_id.strip()
    else:
        if cv_file is None or not jd_text.strip():
            raise HTTPException(422, "Cần gửi cv_file + jd_text hoặc app_id đã có")

        score_response = await api_score_cv(
            cv_file=cv_file,
            jd_text=jd_text,
            mode=mode,
            use_cache=use_cache,
            level=level,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_id=candidate_id,
            # Nếu chưa có app_id thì phải chấm CV thật trước khi tạo link,
            # không tạo hồ sơ với điểm mặc định 10/10.
            skip_scoring=False,
            authorization=authorization,
            idempotency_key=f"{idempotency_key}:score" if idempotency_key else None,
        )
        score_data = json.loads(score_response.body)
        app_id = score_data["app_id"]

    # --- 1. Cấu hình và sinh câu hỏi ---
    config = {
        "PART_1_DEFAULT": part1_limit,
        "PART_2_GENERATED": part2_limit,
        "PART_3_FOLLOW_UP": part3_limit
    }
    with db() as conn:
        conn.execute(
            "UPDATE cv_applications SET interview_config=?, prep_status='generating', prep_error=NULL WHERE id=?",
            (json.dumps(config), app_id)
        )
        conn.execute("DELETE FROM interview_prep WHERE app_ref=?", (app_id,))

    from backend.services.prep_service import _create_prep
    try:
        prep_data = await _create_prep(position_id or "default", app_id, level=level)
        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET prep_status='ready', prep_error=NULL WHERE id=?",
                (app_id,),
            )
    except Exception as e:
        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET prep_status='error', prep_error=? WHERE id=?",
                (str(e), app_id),
            )
        raise HTTPException(500, f"Lỗi sinh câu hỏi: {str(e)}")

    part1_actual = len([k for k in prep_data.get("questions", {}).keys() if str(k).startswith("1.")])
    part2_actual = len([k for k in prep_data.get("questions", {}).keys() if str(k).startswith("2.")])
    part3_actual = prep_data.get("follow_up_limit", part3_limit)

    # --- 2. Lấy link phỏng vấn ---
    schedule_response = await api_schedule_interview(
        ScheduleRequest(
            app_id=app_id,
            start_time=start_time,
            end_time=end_time,
            position_id=position_id,
            level=level,
        ),
        authorization=authorization,
        idempotency_key=f"{idempotency_key}:schedule" if idempotency_key else None,
    )
    schedule_data = json.loads(schedule_response.body.decode('utf-8'))
    return JSONResponse({
        "schedule": schedule_data,
        "questions_count": {
            "part1": part1_actual,
            "part2": part2_actual,
            "part3": part3_actual
        },
        "questions": {
            k: {"text": v.get("text"), "type": v.get("type")}
            for k, v in prep_data.get("questions", {}).items()
        }
    })


# ─────────────────────────────────────────────────────────────
# 3. GET /api/v1/report/{app_id}
#    Báo cáo kết quả theo mã ứng viên (app_id từ /score-cv)
# ─────────────────────────────────────────────────────────────
@router.get("/report/{app_id}")
def api_get_report(
    app_id: str,
    authorization: str = Header(None),
):
    """
    **Lấy báo cáo kết quả đầy đủ theo mã ứng viên.**

    Trả về:
    - Điểm CV, tiêu chí, tóm tắt AI
    - Phản hồi của ứng viên (nếu đã trả lời câu hỏi chuyên sâu)
    - Kết quả phỏng vấn nếu đã phỏng vấn (transcript, điểm, incidents)
    - Câu hỏi HOD

    **Auth:** `Authorization: Bearer <api_key>`
    (Tương thích cũ: `Authorization: token <user_id>:<api_key>`)
    """
    tenant = _require_tenant(authorization)

    with db() as conn:
        app = conn.execute(
            "SELECT * FROM cv_applications WHERE id=? AND company_id=?", (app_id, tenant["company_id"])
        ).fetchone()
        if not app:
            raise HTTPException(404, f"Không tìm thấy app_id='{app_id}'")

        app_dict = dict(app)

        # Parse score_breakdown
        score_breakdown = {}
        if app_dict.get("score_breakdown"):
            try:
                score_breakdown = json.loads(app_dict["score_breakdown"])
            except Exception:
                pass

        # Chỉ lấy interview liên kết bằng app_id; không dùng email fallback để tránh lộ dữ liệu tenant khác.
        iv_rows = conn.execute("""
            SELECT DISTINCT i.*, c.name AS cname, c.email AS cemail
            FROM interviews i
            LEFT JOIN interview_prep p ON i.prep_id = p.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            WHERE p.app_ref = ?
               OR i.candidate_id = ?
            ORDER BY i.submitted_at DESC
            LIMIT 5
        """, (app_id, app_id)).fetchall()

        interviews_out = []
        for iv in iv_rows:
            iv_dict = dict(iv)
            answers = conn.execute("""
                SELECT question_number, question_type, question_text,
                       transcript, ai_level, ai_feedback,
                       score, notes, duration_sec, time_spent, attempt_number
                FROM answers
                WHERE interview_id = ?
                ORDER BY attempt_number, question_number
            """, (iv_dict["id"],)).fetchall()

            incidents = conn.execute("""
                SELECT type, description, created_at
                FROM incidents WHERE interview_id = ?
                ORDER BY created_at
            """, (iv_dict["id"],)).fetchall()

            hod_questions = []
            if iv_dict.get("hod_questions"):
                try:
                    hod_questions = json.loads(iv_dict["hod_questions"])
                except Exception:
                    pass

            grouped_scores = {}
            score_map = {"nắm vững": 10.0, "am hiểu": 7.5, "có biết qua": 5.0, "không biết": 0.0}
            for a in answers:
                level_name = a["ai_level"]
                if level_name not in score_map:
                    continue
                base_qn = str(a["question_number"] or "").split(".", 1)[0]
                group_key = f"{a['attempt_number'] or 1}:{base_qn}"
                score_value = score_map[level_name]
                group = grouped_scores.setdefault(group_key, {"base_score": None, "follow_up_scores": []})
                if "." in str(a["question_number"] or ""):
                    group["follow_up_scores"].append(score_value)
                else:
                    group["base_score"] = score_value
            group_averages = []
            for group in grouped_scores.values():
                base_score = group["base_score"]
                included_scores = group["follow_up_scores"] if base_score is None else [base_score, *(value for value in group["follow_up_scores"] if value > base_score)]
                if included_scores:
                    group_averages.append(sum(included_scores) / len(included_scores))
            interview_avg_score = round(sum(group_averages) / len(group_averages), 2) if group_averages else 0

            interviews_out.append({
                "interview_id": iv_dict["id"],
                "status": iv_dict["status"],
                "submitted_at": iv_dict["submitted_at"],
                "level": iv_dict.get("level"),
                "avg_score": interview_avg_score,
                "tab_switches": iv_dict.get("tab_switches", 0),
                "overall_strengths": iv_dict.get("overall_strengths"),
                "overall_weaknesses": iv_dict.get("overall_weaknesses"),
                "answers": [
                    {
                        "question_number": a["question_number"],
                        "question_type": a["question_type"],
                        "question_text": a["question_text"],
                        "transcript": a["transcript"],
                        "ai_level": a["ai_level"],
                        "ai_feedback": a["ai_feedback"],
                        "score": a["score"],
                        "notes": a["notes"],
                        "duration_sec": a["duration_sec"],
                        "time_spent_sec": a["time_spent"],
                    }
                    for a in answers
                ],
                "incidents": [dict(i) for i in incidents],
                "hod_questions": hod_questions,
            })

    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='cv_pass_score'").fetchone()
        current_pass_score = float(row["value"]) if row else PASS_SCORE
        if current_pass_score > 5:
            current_pass_score = current_pass_score / 2
    cv_score = app_dict.get("cv_score") or 0
    if cv_score > 5:
        cv_score = cv_score / 2
    extracted_info = {}
    if app_dict.get("cv_extracted_info"):
        try:
            extracted_info = json.loads(app_dict["cv_extracted_info"])
        except Exception:
            pass

    return JSONResponse({
        "app_id": app_id,
        "candidate": {
            "name": app_dict.get("name"),
            "email": app_dict.get("email"),
            "phone": app_dict.get("phone"),
            "cv_extracted_info": extracted_info,
        },
        "job_id": app_dict.get("job_id"),
        "level": app_dict.get("level"),
        "applied_at": app_dict.get("applied_at"),
        "status": app_dict.get("status"),
        "interview_link": app_dict.get("interview_link"),
        "interview_slot_token": app_dict.get("interview_slot_token"),
        "interview_link_sent_at": app_dict.get("interview_link_sent_at"),
        "interview_link_source": app_dict.get("interview_link_source"),
        "cv_score": cv_score,
        "pass_threshold": current_pass_score,
        "verdict": "pass" if cv_score >= current_pass_score else "fail",
        "criteria_scores": score_breakdown.get("criteria_scores", {}),
        "reasons": score_breakdown.get("reasons", {}),
        "summary": score_breakdown.get("summary", app_dict.get("ai_summary", "")),
        "bonus_applied": score_breakdown.get("bonus_applied", False),
        "bonus_points": score_breakdown.get("bonus_points", 0.0),
        "bonus_reason": score_breakdown.get("bonus_reason", ""),
        "deep_questions": score_breakdown.get("deep_questions", []),
        "candidate_reply": score_breakdown.get("candidate_reply"),
        "reply_analysis": score_breakdown.get("reply_analysis"),
        "interviews": interviews_out,
    })

@router.get("/debug-slots")
def debug_slots(authorization: str = Header(None)):
    if os.environ.get("ENABLE_DEBUG_ENDPOINTS", "false").lower() not in {"1", "true", "yes"}:
        raise HTTPException(404, "Không tìm thấy endpoint")
    tenant = _require_tenant(authorization)
    with db() as conn:
        rows = conn.execute("SELECT * FROM interview_slots WHERE company_id=?", (tenant["company_id"],)).fetchall()
        now_utc = datetime.now(timezone.utc)
        results = []
        for r in rows:
            d = dict(r)
            if d["start_time"] and d["end_time"]:
                try:
                    start_dt = parse_slot_datetime(d["start_time"])
                    end_dt = parse_slot_datetime(d["end_time"])
                    d["now_utc"] = now_utc.isoformat()
                    d["is_expired"] = now_utc > end_dt
                    d["is_not_started"] = now_utc < start_dt
                except Exception as e:
                    d["error"] = str(e)
            results.append(d)
        return results


# ─────────────────────────────────────────────────────────────
# Helper nội bộ — validate slot token (dùng bởi trang phỏng vấn)
# GET /api/v1/slot/{token}/validate   (KHÔNG cần auth)
# ─────────────────────────────────────────────────────────────
@router.get("/slot/{token}/validate")
@router.get("/{token}/validate")
def api_validate_slot(token: str):
    """
    Kiểm tra token lịch hẹn còn hiệu lực không.
    Gọi bởi frontend interview.html — không cần Authorization.
    """
    with db() as conn:
        try:
            row = conn.execute(
                "SELECT * FROM interview_slots WHERE token=?", (token,)
            ).fetchone()
        except Exception:
            raise HTTPException(404, {"reason": "invalid", "message": "Bảng lịch hẹn chưa tồn tại"})

    if not row:
        raise HTTPException(404, {"reason": "invalid", "message": "Token không tồn tại"})

    now_utc = datetime.now(timezone.utc)
    if row["start_time"] and row["end_time"]:
        try:
            start_dt = parse_slot_datetime(row["start_time"])
            end_dt   = parse_slot_datetime(row["end_time"])
        except Exception as e:
            raise HTTPException(500, {"reason": "error", "message": f"Lỗi parse thời gian: {e}"})

        if now_utc < start_dt:
            remaining_secs = int((start_dt - now_utc).total_seconds())
            remaining_minutes = max(1, (remaining_secs + 59) // 60)
            raise HTTPException(403, {
                "reason": "not_started",
                "message": f"Buổi phỏng vấn chưa bắt đầu. Còn khoảng {remaining_minutes} phút nữa.",
                "start_time": start_dt.isoformat(),
            })

        if now_utc > end_dt:
            raise HTTPException(403, {
                "reason": "expired",
                "message": "Khung giờ phỏng vấn đã kết thúc. Vui lòng liên hệ HR để đặt lại lịch.",
                "end_time": end_dt.isoformat(),
            })

    expiry = int(end_dt.timestamp()) if row["end_time"] else int(time.time()) + 4 * 60 * 60
    from backend.services.interview_access import issue
    return {
        "valid": True,
        "app_id": row["app_id"],
        "position_id": row["position_id"],
        "level": row["level"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "interview_session": issue(row["app_id"], token, expiry),
    }
