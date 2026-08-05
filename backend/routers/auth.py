import hashlib
import json
import os
import re
import secrets
import time
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from backend.config import ADMIN_KEY
from backend.database import db

router = APIRouter(prefix="/auth", tags=["Auth"])


def _parse_log_rows(rows):
    logs = []
    for r in rows:
        item = dict(r)
        if item.get("details"):
            try:
                item["details"] = json.loads(item["details"])
            except Exception:
                pass
        logs.append(item)
    return logs


def _interview_status_log(iv):
    status = (iv["status"] or "").strip() or "pending_review"
    event_type = {
        "submitted": "interview_submitted",
        "evaluated": "interview_evaluated",
        "pending_reinterview": "reinterview_requested",
        "pending_review": "interview_pending_review",
    }.get(status, "interview_status")
    message = {
        "submitted": "Ứng viên đã nộp bài phỏng vấn, hệ thống đang xử lý.",
        "evaluated": "AI đã đánh giá xong bài phỏng vấn.",
        "pending_reinterview": "HR đã yêu cầu ứng viên phỏng vấn bổ sung.",
        "pending_review": "Bài phỏng vấn đang chờ xét duyệt.",
    }.get(status, f"Trạng thái phỏng vấn đã cập nhật: {status}.")
    return {
        "id": f"interview-status:{iv['id']}:{status}",
        "app_id": iv["app_ref"],
        "email": iv["email"],
        "event_type": event_type,
        "message": message,
        "details": {
            "interview_id": iv["id"],
            "status": status,
            "position_id": iv["position_id"],
        },
        "created_at": iv["submitted_at"],
    }


def _log_interview_id(log):
    details = log.get("details") or {}
    if not isinstance(details, dict):
        return ""
    return str(details.get("interview_id") or "")


def _group_consecutive_alerts(alerts, gap_seconds=10):
    """
    Gom các alert liên tiếp cùng loại trong vòng gap_seconds giây thành 1 sự cố.
    Trả về list mới với thêm field 'count' (số lần) và 'duration_seconds'.
    Bỏ qua các alert loại 'unknown'.
    """
    from datetime import datetime, timezone

    def parse_ts(val):
        if not val:
            return None
        s = str(val).strip().replace(' ', 'T')
        if not s.endswith('Z') and '+' not in s[10:] and '-' not in s[11:]:
            s += 'Z'
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None

    # Lọc bỏ unknown
    filtered = [a for a in alerts if (a.get('alert_type') or '').lower() not in ('unknown', '')]

    grouped = []
    for alert in filtered:
        t = parse_ts(alert.get('timestamp') or alert.get('created_at'))
        if not grouped:
            grouped.append({**alert, 'count': 1, 'duration_seconds': 0})
            continue
        last = grouped[-1]
        last_t = parse_ts(last.get('timestamp') or last.get('created_at'))
        same_type = last.get('alert_type') == alert.get('alert_type')
        close_in_time = last_t and t and (t - last_t).total_seconds() <= gap_seconds
        if same_type and close_in_time:
            last['count'] = last.get('count', 1) + 1
            if last_t and t:
                last['duration_seconds'] = round((t - last_t).total_seconds() * last['count'])
        else:
            grouped.append({**alert, 'count': 1, 'duration_seconds': 0})

    return grouped


def _collect_interview_proctoring_logs(conn, interview):
    app_id = interview.get("app_ref")
    if not app_id and interview.get("cv_path"):
        m = re.search(r"APP-[A-F0-9]{8}", interview["cv_path"])
        if m:
            app_id = m.group(0)

    alerts = []
    if app_id:
        try:
            session_row = conn.execute(
                """
                SELECT session_id, MAX(id) AS latest_id
                FROM proctoring_alerts
                WHERE session_id=? OR session_id LIKE ?
                GROUP BY session_id
                ORDER BY latest_id DESC
                LIMIT 1
                """,
                (app_id, f"{app_id}:%"),
            ).fetchone()
            session_id = session_row["session_id"] if session_row else None
            raw_alerts = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, session_id, alert_type, snapshot_id, timestamp, created_at
                    FROM proctoring_alerts
                    WHERE session_id=?
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            ] if session_id else []
            alerts = _group_consecutive_alerts(raw_alerts)
        except Exception:
            alerts = []

    return {
        "app_id": app_id,
        "interview_id": interview["id"],
        "tab_switches": interview.get("tab_switches") or 0,
        "proctoring_alerts": alerts,
    }

# ─────────────────────────────────────────────────────────────
# Password Hashing Helpers (PBKDF2 HMAC SHA256)
# ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt_bytes = os.urandom(16)
    salt_hex = salt_bytes.hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        100000
    ).hex()
    return f"{salt_hex}:{pwd_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        if ":" not in stored_hash:
            return False
        salt_hex, pwd_hash = stored_hash.split(":", 1)
        salt_bytes = bytes.fromhex(salt_hex)
        calc_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            100000
        ).hex()
        return secrets.compare_digest(calc_hash, pwd_hash)
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────
class CheckUserReq(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None

class RegisterReq(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str

class LoginReq(BaseModel):
    account: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.post("/check-user")
def check_user(req: CheckUserReq):
    email = (req.email or "").strip().lower()
    phone = (req.phone or "").strip()

    if not email and not phone:
        raise HTTPException(400, "Vui lòng nhập Email hoặc Số điện thoại")

    user_row = None
    with db() as conn:
        if email:
            user_row = conn.execute(
                "SELECT id, name, email, phone, role FROM users WHERE LOWER(email) = ?", (email,)
            ).fetchone()
        if not user_row and phone:
            user_row = conn.execute(
                "SELECT id, name, email, phone, role FROM users WHERE phone = ?", (phone,)
            ).fetchone()
        
        # Nếu chưa có trong bảng users, kiểm tra lịch sử cv_applications
        app_row = None
        if not user_row:
            if email:
                app_row = conn.execute(
                    "SELECT name, email, phone FROM cv_applications WHERE LOWER(email) = ? ORDER BY applied_at DESC LIMIT 1", (email,)
                ).fetchone()
            if not app_row and phone:
                app_row = conn.execute(
                    "SELECT name, email, phone FROM cv_applications WHERE phone = ? ORDER BY applied_at DESC LIMIT 1", (phone,)
                ).fetchone()

    if user_row:
        u = dict(user_row)
        return {
            "exists": True,
            "has_account": True,
            "user": {
                "name": u["name"],
                "email": u["email"],
                "phone": u["phone"],
                "role": u["role"]
            }
        }

    if app_row:
        a = dict(app_row)
        return {
            "exists": True,
            "has_account": False, # Có lịch sử nhưng chưa đăng ký tài khoản (chưa có pass)
            "user": {
                "name": a["name"],
                "email": a["email"],
                "phone": a["phone"]
            }
        }

    return {
        "exists": False,
        "has_account": False,
        "user": None
    }


@router.post("/register")
def register_user(req: RegisterReq):
    name = req.name.strip()
    email = req.email.strip().lower()
    phone = req.phone.strip()
    password = req.password.strip()

    if not name or not email or not password:
        raise HTTPException(400, "Vui lòng điền đầy đủ Tên, Email và Mật khẩu")
    if len(password) < 6:
        raise HTTPException(400, "Mật khẩu phải có ít nhất 6 ký tự")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    user_id = "USR-" + uuid.uuid4().hex[:10].upper()
    pwd_hash = hash_password(password)

    with db() as conn:
        # Kiểm tra trùng email hoặc sđt trong users
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(email) = ? OR (phone != '' AND phone = ?)", (email, phone)
        ).fetchone()
        if existing:
            raise HTTPException(400, "Email hoặc Số điện thoại đã được đăng ký tài khoản")

        conn.execute(
            "INSERT INTO users (id, email, phone, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, email, phone, pwd_hash, name, "candidate", now)
        )

    return {
        "success": True,
        "message": "Tạo tài khoản thành công!",
        "token": user_id,
        "user": {
            "id": user_id,
            "name": name,
            "email": email,
            "phone": phone,
            "role": "candidate"
        }
    }


@router.post("/login")
def login_user(req: LoginReq):
    account = (req.account or req.email or req.phone or "").strip().lower()
    password = (req.password or "").strip()

    if not account or not password:
        raise HTTPException(400, "Vui lòng nhập Email/SĐT và Mật khẩu")

    with db() as conn:
        user_row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = ? OR phone = ?", (account, account)
        ).fetchone()

    if not user_row:
        raise HTTPException(401, "Tài khoản không tồn tại. Vui lòng đăng ký!")

    user = dict(user_row)
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Mật khẩu không chính xác!")

    admin_key = ADMIN_KEY if user.get("role") == "admin" else None

    return {
        "success": True,
        "token": user["id"],
        "admin_key": admin_key,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "role": user.get("role", "candidate")
        }
    }


@router.get("/history")
def get_user_history(
    email: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None)
):
    user_email = (email or "").strip().lower()
    user_phone = (phone or "").strip()

    # Nếu có x_user_id, lấy email/phone từ user
    if x_user_id:
        with db() as conn:
            u = conn.execute("SELECT email, phone FROM users WHERE id=?", (x_user_id,)).fetchone()
            if u:
                user_email = u["email"] or user_email
                user_phone = u["phone"] or user_phone

    if not user_email and not user_phone:
        raise HTTPException(400, "Cần cung cấp Email hoặc SĐT để xem lịch sử")

    with db() as conn:
        u_row = conn.execute("SELECT name FROM users WHERE LOWER(email) = ? OR (phone != '' AND phone = ?)", (user_email, user_phone)).fetchone()
        u_name = u_row["name"] if u_row else ""

        # Fetch full application details
        apps = conn.execute("""
            SELECT id, job_id, name, email, phone, cv_filename, cv_path, cv_score, score_breakdown, ai_summary, status, applied_at, is_reapplicant, prev_app_id, level, eval_round1_status, eval_round2_status, eval_round3_status
            FROM cv_applications
            WHERE LOWER(email) = ? OR (phone != '' AND phone = ?) OR (? != '' AND name = ?)
            ORDER BY applied_at DESC
        """, (user_email, user_phone, u_name, u_name)).fetchall()
        app_ids = [a["id"] for a in apps]
        log_rows = []
        if user_email or app_ids:
            clauses = []
            params = []
            if user_email:
                clauses.append("LOWER(email) = ?")
                params.append(user_email)
            if app_ids:
                clauses.append(f"app_id IN ({','.join('?' for _ in app_ids)})")
                params.extend(app_ids)
            log_rows = conn.execute(
                f"""
                SELECT * FROM application_logs
                WHERE {' OR '.join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT 200
                """,
                params,
            ).fetchall()
        logs_by_app = {}
        logs_all = _parse_log_rows(log_rows)
        for item in logs_all:
            logs_by_app.setdefault(item.get("app_id") or "", []).append(item)

        # Fetch full interview details
        interviews = conn.execute("""
            SELECT i.id, i.candidate_id, i.position_id, i.cv_filename, i.cv_path, i.status, i.submitted_at, i.prep_id, i.level,
                   i.hod_questions, i.tab_switches, i.video_path,
                   i.overall_strengths AS strength_analysis, 
                   i.overall_weaknesses AS weakness_analysis, 
                   i.overall_competencies AS outstanding_competencies, 
                   c.name, c.email,
                   p.app_ref
            FROM interviews i
            JOIN candidates c ON i.candidate_id = c.id
            LEFT JOIN interview_prep p ON p.id = i.prep_id
            WHERE LOWER(c.email) = ? OR (? != '' AND c.name = ?)
            ORDER BY i.submitted_at DESC
        """, (user_email, u_name, u_name)).fetchall()

        app_list = []
        for a in apps:
            ad = dict(a)
            if ad.get("cv_score") is not None:
                try:
                    ad["cv_score"] = round(float(ad["cv_score"]), 1)
                except Exception:
                    pass
            email_logs = [log for log in logs_all if (log.get("email") or "").lower() == (ad.get("email") or "").lower()]
            own_logs = logs_by_app.get(ad["id"], [])
            current_logs = [*email_logs, *own_logs]
            existing_interview_events = {
                (log.get("event_type"), _log_interview_id(log))
                for log in current_logs
            }
            interview_logs = []
            for iv in interviews:
                same_app = iv["app_ref"] and iv["app_ref"] == ad["id"]
                same_position = (iv["email"] or "").lower() == (ad.get("email") or "").lower() and iv["position_id"] == ad["job_id"]
                if not same_app and not same_position:
                    continue
                status_log = _interview_status_log(iv)
                event_key = (status_log["event_type"], str(status_log["details"]["interview_id"]))
                if event_key not in existing_interview_events:
                    interview_logs.append(status_log)
            merged = {log.get("id"): log for log in [*current_logs, *interview_logs]}
            ad["application_logs"] = sorted(merged.values(), key=lambda x: x.get("created_at") or "", reverse=True)
            app_list.append(ad)

        interview_list = []
        for iv in interviews:
            ivd = dict(iv)
            ans_rows = conn.execute("""
                SELECT question_number, question_text, transcript, audio_path, duration_sec, time_spent
                FROM answers
                WHERE interview_id = ?
                ORDER BY question_number ASC
            """, (ivd["id"],)).fetchall()
            ivd["answers"] = [dict(a) for a in ans_rows]
            ivd["proctoring_logs"] = _collect_interview_proctoring_logs(conn, ivd)
            interview_list.append(ivd)

    return {
        "applications": app_list,
        "interviews": interview_list
    }
