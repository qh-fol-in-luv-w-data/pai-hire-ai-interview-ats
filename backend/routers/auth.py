import hashlib
import json
import os
import re
import secrets
import time
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query, Request, Response
from pydantic import BaseModel
from backend.database import db
from backend.services.auth_service import create_session, current_user, revoke_session
from backend.services.email_service import send_password_reset_email

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

class UpdateProfileReq(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: str
    account_type: str = "user"

class PasswordResetConfirm(BaseModel):
    token: str
    account_type: str = "user"
    password: str

_RESET_TTL_SECONDS = 60 * 60

def _reset_account_type(value: str) -> str:
    value = (value or "user").strip().lower()
    if value not in {"user", "enterprise"}:
        raise HTTPException(422, "Loại tài khoản không hợp lệ")
    return value

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
                    "SELECT name, email, phone FROM cv_applications WHERE LOWER(email) = ? AND COALESCE(application_source,'') != 'api' ORDER BY applied_at DESC LIMIT 1", (email,)
                ).fetchone()
            if not app_row and phone:
                app_row = conn.execute(
                    "SELECT name, email, phone FROM cv_applications WHERE phone = ? AND COALESCE(application_source,'') != 'api' ORDER BY applied_at DESC LIMIT 1", (phone,)
                ).fetchone()

    # Do not disclose somebody else's name/contact details through an account
    # enumeration endpoint.  The UI only needs to decide login vs register.
    return {"exists": bool(user_row or app_row), "has_account": bool(user_row), "user": None}


def _auth_response(user: dict, response: Response):
    token = create_session(user["id"])
    response.set_cookie(
        "pai_session", token, httponly=True, secure=os.environ.get("COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
        samesite="lax", max_age=60 * 60 * 24 * 14, path="/",
    )
    return {
        "success": True,
        # Kept for old clients, but this is an opaque session, never a user id.
        "token": token,
        "user": {key: user.get(key) for key in ("id", "name", "email", "phone", "role")},
    }

@router.post("/register")
def register_user(req: RegisterReq, response: Response):
    name = req.name.strip()
    email = (req.email or "").strip().lower()
    phone = (req.phone or "").strip()
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

    result = _auth_response({"id": user_id, "name": name, "email": email, "phone": phone, "role": "candidate"}, response)
    result["message"] = "Tạo tài khoản thành công!"
    return result


@router.post("/login")
def login_user(req: LoginReq, response: Response):
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

    return _auth_response(user, response)


@router.post("/password-reset/request")
def request_password_reset(req: PasswordResetRequest, request: Request):
    """Issue a one-time reset token without revealing whether an email exists."""
    email = req.email.strip().lower()
    account_type = _reset_account_type(req.account_type)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Email không hợp lệ")
    table = "enterprise_accounts" if account_type == "enterprise" else "users"
    with db() as conn:
        account = conn.execute(f"SELECT id,email FROM {table} WHERE LOWER(email)=LOWER(?)", (email,)).fetchone()
        if account:
            # Six-digit OTP is sent only to the registered mailbox; the DB
            # stores its SHA-256 hash, never the code itself.
            raw_token = f"{secrets.randbelow(1_000_000):06d}"
            now = int(time.time())
            conn.execute(
                "UPDATE password_reset_tokens SET used_at=? WHERE account_type=? AND account_id=? AND used_at IS NULL",
                (now, account_type, account["id"]),
            )
            conn.execute(
                "INSERT INTO password_reset_tokens (id,account_type,account_id,token_hash,created_at,expires_at,requested_ip) VALUES (?,?,?,?,?,?,?)",
                ("PRT-" + uuid.uuid4().hex[:16].upper(), account_type, account["id"], hashlib.sha256(raw_token.encode()).hexdigest(), now, now + _RESET_TTL_SECONDS, request.client.host if request.client else None),
            )
            label = "tài khoản doanh nghiệp" if account_type == "enterprise" else "tài khoản PAI Hire"
            send_password_reset_email(account["email"], raw_token, account_label=label)
        else:
            raise HTTPException(404, "Không tìm thấy tài khoản với email này")
    return {"success": True, "message": "Mã xác nhận đã được gửi đến email của bạn. Mã có hiệu lực 60 phút."}


@router.post("/password-reset/confirm")
def confirm_password_reset(req: PasswordResetConfirm):
    account_type = _reset_account_type(req.account_type)
    token = (req.token or "").strip()
    password = req.password or ""
    minimum = 10 if account_type == "enterprise" else 6
    if not re.fullmatch(r"\d{6}", token):
        raise HTTPException(400, "Mã xác nhận phải gồm 6 chữ số")
    if len(password) < minimum:
        raise HTTPException(422, f"Mật khẩu phải có ít nhất {minimum} ký tự")
    now = int(time.time())
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        row = conn.execute(
            "SELECT id,account_id FROM password_reset_tokens WHERE token_hash=? AND account_type=? AND used_at IS NULL AND expires_at>?",
            (token_hash, account_type, now),
        ).fetchone()
        if not row:
            raise HTTPException(400, "Mã xác nhận không chính xác, đã hết hạn hoặc đã được sử dụng")
        table = "enterprise_accounts" if account_type == "enterprise" else "users"
        
        current_account = conn.execute(f"SELECT password_hash FROM {table} WHERE id=?", (row["account_id"],)).fetchone()
        if current_account and verify_password(password, current_account["password_hash"]):
            raise HTTPException(400, "Mật khẩu mới không được trùng với mật khẩu cũ")
            
        conn.execute(f"UPDATE {table} SET password_hash=? WHERE id=?", (hash_password(password), row["account_id"]))
        conn.execute("UPDATE password_reset_tokens SET used_at=? WHERE id=?", (now, row["id"]))
        if account_type == "enterprise":
            conn.execute("UPDATE enterprise_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL", (now, row["account_id"]))
        else:
            conn.execute("UPDATE user_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, row["account_id"]))
    return {"success": True, "message": "Đã đặt lại mật khẩu. Vui lòng đăng nhập lại."}


@router.post("/logout")
def logout(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    raw = request.cookies.get("pai_session") or ((authorization or "").split(" ", 1)[1].strip() if (authorization or "").lower().startswith("bearer ") else "")
    revoke_session(raw)
    response.delete_cookie("pai_session", path="/")
    return {"success": True}

@router.patch("/profile")
def update_profile(req: UpdateProfileReq, request: Request, authorization: Optional[str] = Header(None), x_user_id: Optional[str] = Header(None)):
    """Cập nhật thông tin tài khoản ứng viên đang đăng nhập."""
    actor = current_user(request, authorization, x_user_id)
    user_id = actor["id"]
    name = req.name.strip()
    email = (req.email or "").strip().lower()
    phone = (req.phone or "").strip()
    if len(name) < 2:
        raise HTTPException(400, "Họ tên phải có ít nhất 2 ký tự")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Email không hợp lệ")
    with db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "Không tìm thấy tài khoản")
        duplicate = conn.execute(
            "SELECT id FROM users WHERE id!=? AND ((? != '' AND LOWER(email)=?) OR (? != '' AND phone=?))",
            (user_id, email, email, phone, phone),
        ).fetchone()
        if duplicate:
            raise HTTPException(400, "Email hoặc số điện thoại đã được sử dụng")
        conn.execute("UPDATE users SET name=?, email=?, phone=? WHERE id=?", (name, email, phone, user_id))
        saved = conn.execute("SELECT id, name, email, phone, role FROM users WHERE id=?", (user_id,)).fetchone()
    return {"user": dict(saved)}


@router.get("/history")
def get_user_history(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    actor = current_user(request, authorization, x_user_id)
    user_email = (actor.get("email") or "").strip().lower()
    user_phone = (actor.get("phone") or "").strip()
    if not user_email and not user_phone:
        raise HTTPException(400, "Tài khoản chưa có email hoặc số điện thoại")

    with db() as conn:
        u_row = conn.execute("SELECT name FROM users WHERE LOWER(email) = ? OR (phone != '' AND phone = ?)", (user_email, user_phone)).fetchone()
        u_name = u_row["name"] if u_row else ""

        # Fetch full application details
        apps = conn.execute("""
            SELECT id, job_id, name, email, phone, cv_filename, cv_path, cv_score, score_breakdown, ai_summary, status, applied_at, is_reapplicant, prev_app_id, level, eval_round1_status, eval_round2_status, eval_round3_status
            FROM cv_applications
            WHERE COALESCE(application_source,'') != 'api'
              AND (LOWER(email) = ? OR (phone != '' AND phone = ?) OR (? != '' AND name = ?))
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
            
            candidate_logs = []
            for log in sorted(merged.values(), key=lambda x: x.get("created_at") or "", reverse=True):
                evt = log.get("event_type", "")
                
                # Bỏ qua các log nội bộ không cho ứng viên xem
                if evt in ["cv_score_error", "questions_error", "questions_edited", "questions_ready", "hr_reviewed"]:
                    continue
                    
                msg = log.get("message", "")
                if evt == "app_received":
                    msg = "Hồ sơ của bạn đã được hệ thống tiếp nhận thành công."
                elif evt in ["cv_scored", "ai_scored"]:
                    msg = "Hồ sơ đang trong quá trình phân tích và đánh giá sơ bộ."
                elif evt == "interview_email_sent":
                    msg = "Chúc mừng! Bạn đã được mời tham gia phỏng vấn. Vui lòng kiểm tra email của bạn."
                elif evt == "interview_submitted":
                    msg = "Bài phỏng vấn của bạn đã được nộp thành công và đang chờ kết quả."
                elif evt == "interview_evaluated":
                    msg = "Bài phỏng vấn đang được hệ thống đánh giá."
                elif evt == "interview_pending_review":
                    msg = "Bài phỏng vấn đang chờ bộ phận tuyển dụng xét duyệt."
                elif evt == "reinterview_requested":
                    msg = "Bộ phận tuyển dụng đã yêu cầu bạn bổ sung thông tin phỏng vấn."
                elif evt == "status_updated":
                    status = (log.get("details") or {}).get("status", "")
                    if status in ["failed", "rejected"]:
                        msg = "Hồ sơ chưa phù hợp ở thời điểm hiện tại. Cảm ơn bạn đã quan tâm."
                    elif status == "passed":
                        msg = "Chúc mừng! Hồ sơ của bạn đã vượt qua vòng đánh giá."
                        
                candidate_logs.append({**log, "message": msg, "details": {}})
                
            ad["application_logs"] = candidate_logs
            # Chỉ trả dữ liệu cần cho ứng viên theo dõi hồ sơ. Các trường phân tích
            # nội bộ (breakdown, AI summary, đường dẫn file) không đi qua endpoint này.
            app_list.append({
                "id": ad["id"],
                "job_id": ad["job_id"],
                "name": ad["name"],
                "email": ad["email"],
                "phone": ad["phone"],
                "cv_filename": ad["cv_filename"],
                "cv_score": ad["cv_score"],
                "status": ad["status"],
                "applied_at": ad["applied_at"],
                "is_reapplicant": ad["is_reapplicant"],
                "level": ad["level"],
                "application_logs": ad["application_logs"],
            })

        interview_list = []
        for iv in interviews:
            ivd = dict(iv)
            ans_rows = conn.execute("""
                SELECT question_number, question_text, transcript, duration_sec, time_spent
                FROM answers
                WHERE interview_id = ?
                ORDER BY question_number ASC
            """, (ivd["id"],)).fetchall()
            monitoring = _collect_interview_proctoring_logs(conn, ivd)
            # Ứng viên được xem lại nội dung mình đã trả lời và tín hiệu giám sát,
            # nhưng tuyệt đối không nhận điểm AI, nhận xét hay đánh giá của HR.
            interview_list.append({
                "id": ivd["id"],
                "position_id": ivd["position_id"],
                "level": ivd["level"],
                "status": ivd["status"],
                "submitted_at": ivd["submitted_at"],
                "tab_switches": ivd["tab_switches"] or 0,
                "answers": [
                    {
                        "question_number": a["question_number"],
                        "question_text": a["question_text"],
                        "transcript": a["transcript"],
                        "duration_sec": a["duration_sec"],
                        "time_spent": a["time_spent"],
                    }
                    for a in ans_rows
                ],
                "proctoring_logs": {
                    "tab_switches": monitoring["tab_switches"],
                    "proctoring_alerts": [
                        {
                            "alert_type": alert.get("alert_type"),
                            "count": alert.get("count", 1),
                            "duration_seconds": alert.get("duration_seconds", 0),
                            "timestamp": alert.get("timestamp") or alert.get("created_at"),
                        }
                        for alert in monitoring["proctoring_alerts"]
                    ],
                },
            })

    return {
        "applications": app_list,
        "interviews": interview_list
    }
