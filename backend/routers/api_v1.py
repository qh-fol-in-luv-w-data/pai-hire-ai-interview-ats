"""
PAI HR — External API v1
========================
Auth: Header  Authorization: token <user_id>:<api_key>

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

from backend.database import db
from backend.config import (
    BASE_DIR,
    CV_UPLOAD_DIR,
    INTERVIEW_URL,
    OPENAI_API_KEY,
    SCORE_PROMPT,
    DEEP_ANALYSIS_PROMPT,
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
        raise HTTPException(500, "API_TOKEN chưa được cấu hình")
    return token


def _require_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "Thiếu Authorization header")
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, "Authorization phải có dạng: Bearer <token>")
    token = parts[1]
    if not compare_digest(token, _get_valid_token()):
        raise HTTPException(401, "Token không hợp lệ")
    return token


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
@router.post("/score-cv")
async def api_score_cv(
    cv_file: UploadFile = File(..., description="File CV (PDF/DOCX)"),
    jd_text: str = Form(..., description="Nội dung mô tả công việc (JD) dạng text thuần"),
    mode: str = Form("candidate", description="'candidate' (ứng viên) hoặc 'employee' (nhân viên nội bộ)"),
    use_cache: str = Form("FALSE", description="'TRUE' để dùng cache, tránh gọi AI lặp lại"),
    level: str = Form("Junior", description="Cấp bậc: Entry/Junior/Mid/Senior/Manager/Director"),
    candidate_name: str = Form("", description="Tên ứng viên (tuỳ chọn)"),
    candidate_email: str = Form("", description="Email ứng viên (tuỳ chọn)"),
    authorization: str = Header(None),
):
    """
    **Chấm điểm CV theo JD text và sinh câu hỏi phỏng vấn.**

    - Nhận file CV (PDF/DOCX) và nội dung JD dạng text tự do
    - Hỗ trợ `mode=employee` để điều chỉnh prompt phù hợp đánh giá nội bộ
    - Bật `use_cache=TRUE` để tái dùng kết quả nếu cùng CV + JD đã từng chấm

    **Auth:** `Authorization: token <user_id>:<api_key>`
    """
    _require_token(authorization)

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
    ck = _cache_key(cv_bytes, jd_text, mode)
    if use_cache_flag and ck in _SCORE_CACHE:
        cached = _SCORE_CACHE[ck]
        return JSONResponse({**cached, "cached": True})

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

    # --- Lấy pass score từ settings ---
    pass_score = PASS_SCORE
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='cv_pass_score'").fetchone()
        if row and row["value"]:
            try:
                pass_score = float(row["value"])
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
            max_tokens=1500,
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
    deep_questions = []
    try:
        deep_prompt = DEEP_ANALYSIS_PROMPT.format(
            cv_text=cv_text[:5000],
            jd_text=jd_text[:3000],
        )
        dq_resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": deep_prompt}],
            temperature=0.5,
            max_tokens=1200,
        )
        dq_raw = dq_resp.choices[0].message.content.strip()
        dq_raw = re.sub(r"^```(?:json)?\s*", "", dq_raw)
        dq_raw = re.sub(r"\s*```$", "", dq_raw)
        dq_data = json.loads(dq_raw)
        if isinstance(dq_data, list):
            deep_questions = dq_data
        elif isinstance(dq_data, dict):
            deep_questions = dq_data.get("questions", dq_data.get("deep_questions", []))
    except Exception as e:
        print(f"[API v1] Deep questions error: {e}")

    # --- Lưu vào DB ---
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    score_breakdown = {**score_result, "deep_questions": deep_questions}
    # Dùng JD text hash làm job_id tạm thời
    jd_slug = "jd_" + hashlib.md5(jd_text.encode()).hexdigest()[:8]
    with db() as conn:
        conn.execute(
            """INSERT INTO cv_applications
               (id, job_id, name, email, cv_filename, cv_path,
                cv_score, score_breakdown, ai_summary, status, applied_at, level)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                app_id, jd_slug,
                candidate_name or f"Candidate {app_id[-4:]}",
                candidate_email or f"{app_id.lower()}@api.local",
                cv_file.filename or "cv.pdf",
                str(cv_path.relative_to(BASE_DIR)),
                total,
                json.dumps(score_breakdown, ensure_ascii=False),
                score_result.get("summary", ""),
                f"waiting_for_reply_{'passed' if verdict == 'pass' else 'failed'}",
                now,
                level,
            ),
        )

    result = {
        "app_id": app_id,
        "verdict": verdict,
        "score": total,
        "pass_threshold": pass_score,
        "mode": mode,
        "criteria_scores": c,
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
):
    """
    **Tạo link phỏng vấn giới hạn theo khung giờ.**

    Ứng viên chỉ vào được trong khoảng `start_time` → `end_time`.

    **Auth:** `Authorization: token <user_id>:<api_key>`
    """
    _require_token(authorization)

    with db() as conn:
        app = conn.execute(
            "SELECT * FROM cv_applications WHERE id=?", (body.app_id,)
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
                used        INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            """INSERT INTO interview_slots
               (token, app_id, position_id, level, start_time, end_time, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (token, body.app_id, position_id, level,
             start_dt.isoformat(), end_dt.isoformat(), now_str),
        )

    base = INTERVIEW_URL.rsplit("/interview", 1)[0]
    interview_link = f"{base}/interview?slot={token}"

    return JSONResponse({
        "token": token,
        "app_id": body.app_id,
        "interview_url": interview_link,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "note": "Ứng viên chỉ được truy cập link trong khung giờ đã đặt.",
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

    **Auth:** `Authorization: token <user_id>:<api_key>`
    """
    _require_token(authorization)

    with db() as conn:
        app = conn.execute(
            "SELECT * FROM cv_applications WHERE id=?", (app_id,)
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

        # Lấy interview liên kết (qua interview_prep)
        iv_rows = conn.execute("""
            SELECT i.*, c.name AS cname, c.email AS cemail
            FROM interview_prep p
            JOIN interviews i ON i.prep_id = p.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            WHERE p.app_ref = ?
            ORDER BY i.submitted_at DESC
            LIMIT 5
        """, (app_id,)).fetchall()

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

            interviews_out.append({
                "interview_id": iv_dict["id"],
                "status": iv_dict["status"],
                "submitted_at": iv_dict["submitted_at"],
                "level": iv_dict.get("level"),
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

    return JSONResponse({
        "app_id": app_id,
        "candidate": {
            "name": app_dict.get("name"),
            "email": app_dict.get("email"),
            "phone": app_dict.get("phone"),
        },
        "job_id": app_dict.get("job_id"),
        "level": app_dict.get("level"),
        "applied_at": app_dict.get("applied_at"),
        "status": app_dict.get("status"),
        "cv_score": app_dict.get("cv_score"),
        "pass_threshold": current_pass_score,
        "verdict": "pass" if (app_dict.get("cv_score") or 0) >= current_pass_score else "fail",
        "criteria_scores": score_breakdown.get("criteria_scores", {}),
        "reasons": score_breakdown.get("reasons", {}),
        "summary": score_breakdown.get("summary", app_dict.get("ai_summary", "")),
        "deep_questions": score_breakdown.get("deep_questions", []),
        "candidate_reply": score_breakdown.get("candidate_reply"),
        "reply_analysis": score_breakdown.get("reply_analysis"),
        "interviews": interviews_out,
    })


# ─────────────────────────────────────────────────────────────
# Helper nội bộ — validate slot token (dùng bởi trang phỏng vấn)
# GET /api/v1/slot/{token}/validate   (KHÔNG cần auth)
# ─────────────────────────────────────────────────────────────
@router.get("/slot/{token}/validate")
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

    return {
        "valid": True,
        "app_id": row["app_id"],
        "position_id": row["position_id"],
        "level": row["level"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
    }
