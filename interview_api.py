"""
ATS Phỏng Vấn — FastAPI + SQLite
Chạy: pip install fastapi uvicorn python-multipart openai
      python interview_api.py

Database: ats_phongvan.db (tự tạo)
Files:    outputs/interviews/{session_id}/
"""

import json
import os
import re
import smtplib
import sqlite3
import time
import uuid
from contextlib import contextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from hmac import compare_digest
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DB_PATH         = BASE_DIR / "ats_phongvan.db"
OUTPUT_DIR      = BASE_DIR / "outputs" / "interviews"
CV_UPLOAD_DIR   = BASE_DIR / "outputs" / "cv_applications"
JDS_DIR         = BASE_DIR / "JDs_Detailed"
ADMIN_KEY       = os.environ.get("ADMIN_KEY", "")
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
PASS_SCORE      = 7.0
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASS       = os.environ.get("SMTP_PASS", "")
INTERVIEW_URL   = os.environ.get("INTERVIEW_URL", "http://localhost:8000")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_LABELS = {
    "Công_Nghệ_Thông_Tin_(IT)":                            "Công Nghệ Thông Tin",
    "Kinh_Doanh_&_Bán_Hàng_(Sales_&_Business_Development)":"Kinh Doanh & Bán Hàng",
    "Chuỗi_Cung_Ứng_&_Logistics_(Supply_Chain)":           "Chuỗi Cung Ứng & Logistics",
    "Kỹ_Thuật_&_Sản_Xuất_(Engineering_&_Manufacturing)":   "Kỹ Thuật & Sản Xuất",
    "Marketing_&_Truyền_Thông_(Marketing_&_PR)":           "Marketing & Truyền Thông",
    "Nhân_Sự_&_Hành_Chính_(HR_&_Admin)":                   "Nhân Sự & Hành Chính",
    "Thiết_Kế_&_Sáng_Tạo_(Design_&_Creative)":            "Thiết Kế & Sáng Tạo",
    "Tài_Chính_&_Kế_Toán_(Finance_&_Accounting)":          "Tài Chính & Kế Toán",
}

QUESTION_META = {
    "01": "Technical",  "02": "Technical",
    "03": "Soft Skill", "04": "Soft Skill",
    "05": "Experience", "06": "Experience",
}

# ─────────────────────────────────────────────────────────────
# Database setup
# ─────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id         TEXT PRIMARY KEY,
            name       TEXT,
            email      TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interviews (
            id           TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(id),
            position_id  TEXT NOT NULL,
            cv_filename  TEXT,
            cv_path      TEXT,
            status       TEXT NOT NULL DEFAULT 'pending_review',
            submitted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS answers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id    TEXT NOT NULL REFERENCES interviews(id),
            question_number TEXT NOT NULL,
            question_type   TEXT NOT NULL,
            audio_path      TEXT,
            duration_sec    REAL,
            score           INTEGER,
            notes           TEXT,
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cv_applications (
            id              TEXT PRIMARY KEY,
            job_id          TEXT NOT NULL,
            name            TEXT NOT NULL,
            email           TEXT NOT NULL,
            phone           TEXT,
            cv_filename     TEXT,
            cv_path         TEXT,
            cv_score        REAL,
            score_breakdown TEXT,
            ai_summary      TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            applied_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_interviews_candidate ON interviews(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_answers_interview    ON answers(interview_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_job            ON cv_applications(job_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_status         ON cv_applications(status);
        """)
    print(f"[DB] Sẵn sàng: {DB_PATH}")

# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="ATS Phỏng Vấn API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include webhook router
try:
    from backend.routers.webhook import router as webhook_router
    app.include_router(webhook_router)
except ImportError:
    pass

@app.on_event("startup")
def startup():
    init_db()

# ─────────────────────────────────────────────────────────────
# POST /interview/submit
# ─────────────────────────────────────────────────────────────
@app.post("/interview/submit")
async def submit_interview(
    position_id:  str        = Form(...),
    candidate_id: str        = Form(None),   # optional — tự tạo nếu chưa có
    cv_file:      UploadFile = File(...),
    answer_01:    UploadFile = File(...),
    answer_02:    UploadFile = File(...),
    answer_03:    UploadFile = File(...),
    answer_04:    UploadFile = File(...),
    answer_05:    UploadFile = File(...),
    answer_06:    UploadFile = File(...),
):
    now          = time.strftime("%Y-%m-%dT%H:%M:%S")
    interview_id = "IV-" + uuid.uuid4().hex[:10].upper()
    session_dir  = OUTPUT_DIR / interview_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Tạo candidate nếu chưa có
    if not candidate_id:
        candidate_id = "C-" + uuid.uuid4().hex[:8].upper()

    # Lưu CV
    cv_ext      = Path(cv_file.filename).suffix or ".pdf"
    cv_filename = f"cv{cv_ext}"
    cv_path     = session_dir / cv_filename
    cv_path.write_bytes(await cv_file.read())

    # Lưu 6 audio
    audio_uploads = [answer_01, answer_02, answer_03, answer_04, answer_05, answer_06]
    answer_rows   = []
    for i, upload in enumerate(audio_uploads, start=1):
        qn         = f"{i:02d}"
        audio_name = f"answer_{qn}.webm"
        audio_path = session_dir / audio_name
        audio_path.write_bytes(await upload.read())
        answer_rows.append({
            "interview_id":    interview_id,
            "question_number": qn,
            "question_type":   QUESTION_META[qn],
            "audio_path":      str(audio_path.relative_to(BASE_DIR)),
            "created_at":      now,
        })

    # Ghi database
    with db() as conn:
        # Upsert candidate
        conn.execute("""
            INSERT INTO candidates (id, created_at)
            VALUES (?, ?)
            ON CONFLICT(id) DO NOTHING
        """, (candidate_id, now))

        # Insert interview
        conn.execute("""
            INSERT INTO interviews
                (id, candidate_id, position_id, cv_filename, cv_path, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            interview_id, candidate_id, position_id,
            cv_filename, str(cv_path.relative_to(BASE_DIR)), now,
        ))

        # Insert answers
        conn.executemany("""
            INSERT INTO answers
                (interview_id, question_number, question_type, audio_path, created_at)
            VALUES (:interview_id, :question_number, :question_type, :audio_path, :created_at)
        """, answer_rows)

    print(f"[✓] {interview_id} | candidate={candidate_id} | position={position_id}")

    return {
        "ok":            True,
        "interview_id":  interview_id,
        "candidate_id":  candidate_id,
        "answers_saved": len(answer_rows),
    }


# ─────────────────────────────────────────────────────────────
# GET /interview/{interview_id}  — chi tiết 1 buổi
# ─────────────────────────────────────────────────────────────
@app.get("/interview/{interview_id}")
def get_interview(interview_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM interviews WHERE id = ?", (interview_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy interview")

        answers = conn.execute(
            "SELECT * FROM answers WHERE interview_id = ? ORDER BY question_number",
            (interview_id,)
        ).fetchall()

    return {
        **dict(row),
        "answers": [dict(a) for a in answers],
    }


# ─────────────────────────────────────────────────────────────
# GET /candidate/{candidate_id}/interviews  — lịch sử 1 người
# ─────────────────────────────────────────────────────────────
@app.get("/candidate/{candidate_id}/interviews")
def get_candidate_interviews(candidate_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        candidate = conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if not candidate:
            raise HTTPException(404, "Không tìm thấy candidate")

        interviews = conn.execute("""
            SELECT i.id, i.position_id, i.status, i.submitted_at,
                   COUNT(a.id) as answer_count
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            WHERE i.candidate_id = ?
            GROUP BY i.id
            ORDER BY i.submitted_at DESC
        """, (candidate_id,)).fetchall()

    return {
        "candidate_id": candidate_id,
        "total":        len(interviews),
        "interviews":   [dict(r) for r in interviews],
    }


# ─────────────────────────────────────────────────────────────
# GET /interviews  — toàn bộ (HR dashboard)
# ─────────────────────────────────────────────────────────────
@app.get("/interviews")
def list_interviews(status: str = None, position_id: str = None, limit: int = 50, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    where, params = [], []
    if status:
        where.append("i.status = ?");      params.append(status)
    if position_id:
        where.append("i.position_id = ?"); params.append(position_id)

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(f"""
            SELECT i.id, i.candidate_id, i.position_id,
                   i.status, i.submitted_at,
                   COUNT(a.id) as answer_count
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            {clause}
            GROUP BY i.id
            ORDER BY i.submitted_at DESC
            LIMIT ?
        """, (*params, limit)).fetchall()

    return {"total": len(rows), "interviews": [dict(r) for r in rows]}


# ─────────────────────────────────────────────────────────────
# PATCH /interview/{interview_id}/review  — HR chấm điểm
# ─────────────────────────────────────────────────────────────
@app.patch("/interview/{interview_id}/review")
async def review_interview(interview_id: str, body: dict, x_admin_key: str = Header(None)):
    """
    body: {
      "status": "reviewed" | "passed" | "failed",
      "answers": { "01": { "score": 8, "notes": "..." }, ... }
    }
    """
    require_admin(x_admin_key)
    with db() as conn:
        conn.execute(
            "UPDATE interviews SET status = ? WHERE id = ?",
            (body.get("status", "reviewed"), interview_id)
        )
        for qn, review in body.get("answers", {}).items():
            conn.execute("""
                UPDATE answers SET score = ?, notes = ?
                WHERE interview_id = ? AND question_number = ?
            """, (review.get("score"), review.get("notes"), interview_id, qn))

    return {"ok": True, "interview_id": interview_id}


# ─────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    with db() as conn:
        stats = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM candidates)  AS candidates,
                (SELECT COUNT(*) FROM interviews)  AS interviews,
                (SELECT COUNT(*) FROM answers)     AS answers
        """).fetchone()
    return {"status": "ok", "db": DB_PATH.name, **dict(stats)}


# ─────────────────────────────────────────────────────────────
# Helpers — Jobs & JDs
# ─────────────────────────────────────────────────────────────
def get_all_jobs():
    jobs = []
    if not JDS_DIR.exists():
        return jobs
    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat_label = CATEGORY_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " "))
        for jd_file in sorted(cat_dir.glob("*.md")):
            jobs.append({
                "id":           jd_file.stem,
                "title":        jd_file.stem.replace("_", " "),
                "category":     cat_label,
                "category_slug": cat_dir.name,
            })
    return jobs


def get_jd_content(job_id: str) -> str:
    for cat_dir in JDS_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
        f = cat_dir / f"{job_id}.md"
        if f.exists():
            return f.read_text(encoding="utf-8")
    return ""


# ─────────────────────────────────────────────────────────────
# Admin auth
# ─────────────────────────────────────────────────────────────
def require_admin(x_admin_key: str = Header(None)):
    if not ADMIN_KEY:
        raise HTTPException(500, "ADMIN_KEY chưa được cấu hình")
    if not x_admin_key or not compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(401, "Unauthorized — sai admin key")


# ─────────────────────────────────────────────────────────────
# CV text extraction
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────────────────────
def send_pass_email(name: str, to_email: str, job_title: str, app_id: str):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Email] Chưa cấu hình SMTP — bỏ qua gửi mail cho {to_email}")
        return

    interview_link = f"{INTERVIEW_URL}?ref={app_id}"
    job_display    = job_title.replace("_", " ")
    today          = time.strftime("%d/%m/%Y")

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;">

  <!-- Logo bar -->
  <tr><td style="background:#131b2e;padding:24px 40px;display:flex;align-items:center;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#ffffff;font-size:16px;font-weight:700;letter-spacing:-.2px;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Phòng Nhân Sự · Tuyển Dụng</p>
      </td>
    </tr></table>
  </td></tr>

  <!-- Hero -->
  <tr><td style="padding:40px 40px 0;">
    <p style="margin:0 0 6px;color:#6b7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;">Thư mời phỏng vấn</p>
    <h1 style="margin:0 0 20px;color:#111827;font-size:24px;font-weight:700;line-height:1.3;">
      Kính gửi {name},
    </h1>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.75;">
      Cảm ơn bạn đã quan tâm và nộp hồ sơ ứng tuyển vị trí
      <strong style="color:#111827;">{job_display}</strong> tại PAI HR.
    </p>
    <p style="margin:16px 0 0;color:#374151;font-size:15px;line-height:1.75;">
      Sau khi xem xét hồ sơ của bạn, chúng tôi rất vui mừng thông báo rằng bạn đã
      <strong style="color:#0051d5;">đáp ứng các tiêu chí tuyển dụng</strong> của vị trí này
      và được mời tham gia vòng phỏng vấn tiếp theo.
    </p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:28px 40px 0;">
    <div style="height:1px;background:#e5e7eb;"></div>
  </td></tr>

  <!-- Interview info -->
  <tr><td style="padding:28px 40px 0;">
    <p style="margin:0 0 16px;color:#111827;font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">Thông tin buổi phỏng vấn</p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border-radius:8px 8px 0 0;border:1px solid #e5e7eb;border-bottom:none;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Hình thức</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">Phỏng vấn AI trực tuyến</p>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border:1px solid #e5e7eb;border-bottom:none;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Vị trí</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">{job_display}</p>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border-radius:0 0 8px 8px;border:1px solid #e5e7eb;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Thời lượng dự kiến</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">10 – 15 phút</p>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 24px;color:#374151;font-size:14px;line-height:1.75;">
      Bạn có thể thực hiện buổi phỏng vấn bất cứ lúc nào, theo đường link bên dưới.
      Hệ thống sẽ ghi lại câu trả lời của bạn để đội ngũ tuyển dụng đánh giá.
    </p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
      <tr><td align="center">
        <a href="{interview_link}"
           style="display:inline-block;background:#0051d5;color:#ffffff;text-decoration:none;
                  font-weight:700;font-size:15px;padding:15px 40px;border-radius:10px;letter-spacing:-.1px;">
          Bắt đầu phỏng vấn →
        </a>
      </td></tr>
    </table>
    <p style="margin:16px 0 0;text-align:center;font-size:12px;color:#9ca3af;">
      Nếu nút không hoạt động, copy link: <br/>
      <a href="{interview_link}" style="color:#0051d5;word-break:break-all;">{interview_link}</a>
    </p>
  </td></tr>

  <!-- Note -->
  <tr><td style="padding:0 40px 32px;">
    <div style="background:#fffbeb;border-left:3px solid #f59e0b;border-radius:4px;padding:14px 16px;">
      <p style="margin:0;color:#92400e;font-size:13px;line-height:1.6;">
        <strong>Lưu ý:</strong> Link phỏng vấn có hiệu lực trong <strong>7 ngày</strong> kể từ ngày nhận email này.
        Nếu cần hỗ trợ, vui lòng liên hệ đội tuyển dụng.
      </p>
    </div>
  </td></tr>

  <!-- Sig -->
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:13px;">{today}</span>
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;line-height:1.6;">
      Email tự động từ hệ thống PAI HR &nbsp;·&nbsp; Mã hồ sơ: <strong>{app_id}</strong><br/>
      Vui lòng không reply email này.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"]      = f"Thư mời phỏng vấn — {job_display} | PAI HR"
    msg["From"]         = f"PAI HR Tuyển Dụng <{SMTP_USER}>"
    msg["To"]           = to_email
    msg["Reply-To"]     = SMTP_USER
    msg["X-Mailer"]     = "PAI-HR-Mailer/1.0"
    msg["Precedence"]   = "bulk"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"[Email] Đã gửi → {to_email}")
    except Exception as e:
        print(f"[Email Error] {to_email}: {e}")


# ─────────────────────────────────────────────────────────────
# CV scoring (background task)
# ─────────────────────────────────────────────────────────────
SCORE_PROMPT = """\
Bạn là chuyên gia HR cấp cao. Chấm điểm CV ứng viên theo thang 10 điểm dựa trên JD.

=== JOB DESCRIPTION ===
{jd}

=== CV ỨNG VIÊN ===
{cv}

=== TIÊU CHÍ CHẤM ĐIỂM (10 điểm) ===

NHÓM 1 – YẾU TỐ CỨNG (6.5đ):
1.1 Kinh Nghiệm (3.5đ):
  - Số năm (tối đa 2đ): đọc JD để xác định số năm yêu cầu (gọi là Y). Nếu CV ≥ Y → 2đ. Nếu CV ≥ Y/2 → 1đ. Nếu CV < Y/2 → 0đ. Nếu JD chấp nhận fresher/không yêu cầu KN thì bất kỳ KN nào ≥ 0 đều được 2đ.
  - Tính liên quan (1đ): đúng ngành=1, liên quan gần=0.5, liên quan xa=0.25, không=0
  - Thành tích cá nhân (0.5đ): có thành tích cụ thể (giải thưởng, doanh số, dự án nổi bật, được ghi nhận)=0.5, không có=0
1.2 Học Vấn & Chứng Chỉ (2.5đ):
  - Bằng cấp (1đ): đáp ứng YC JD=1, liên quan=0.5, không đáp ứng=0
  - Chuyên ngành (1đ): khớp đúng ngành=1, liên quan=0.5, không liên quan=0
  - Chứng chỉ (0.5đ): đủ=0.5, đủ 50%=0.25, không=0
1.3 Kỹ Năng Chuyên Môn (1đ):
  - Nhiệm vụ khớp JD: 100%=1, 70%=0.75, 50%=0.5, 30%=0.25, không=0

NHÓM 2 – YẾU TỐ MỀM (3đ):
2.1 Chất lượng CV (1đ): cấu trúc rõ ràng, chuyên nghiệp, không lỗi chính tả
2.2 Dự án & Portfolio (1đ): dự án thực tế, side project, minh chứng kết quả
2.3 Lãnh đạo & Teamwork (1đ): kinh nghiệm nhóm, vai trò leadership, đóng góp tập thể


Chỉ trả về JSON thuần (không markdown, không giải thích):
{{
  "total_score": <số thực 0-10, làm tròn bội số 0.25>,
  "group1": {{
    "work_experience": {{"years": <0-2>, "relevance": <0-1>, "achievements": <0 hoặc 0.5>}},
    "education": {{"degree": <0-1>, "major": <0-1>, "certs": <0-0.5>}},
    "technical_skills": <0-1>
  }},
  "group2": {{
    "cv_quality": <0-1>,
    "projects": <0-1>,
    "leadership": <0-1>
  }},
  "summary": "<tóm tắt 80-100 từ tiếng Việt: điểm mạnh và điểm cần cải thiện>",
  "pass": <true nếu total_score >= 7>
}}"""


async def _do_score_cv(app_id: str, cv_path: Path, job_id: str):
    cv_text = extract_cv_text(cv_path)
    jd_text = get_jd_content(job_id)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        prompt = SCORE_PROMPT.format(jd=jd_text[:4000], cv=cv_text[:5000])
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        total  = round(float(result.get("total_score", 0)), 2)
        status = "passed" if total >= PASS_SCORE else "failed"

        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET cv_score=?, score_breakdown=?, ai_summary=?, status=? WHERE id=?",
                (total, json.dumps(result, ensure_ascii=False), result.get("summary", ""), status, app_id),
            )
            row = conn.execute(
                "SELECT name, email, job_id FROM cv_applications WHERE id=?", (app_id,)
            ).fetchone()

        print(f"[CV Score] {app_id} → {total}/10 ({status})")

        if status == "passed" and row:
            send_pass_email(row["name"], row["email"], row["job_id"], app_id)

    except Exception as e:
        print(f"[CV Score Error] {app_id}: {e}")
        with db() as conn:
            conn.execute("UPDATE cv_applications SET status='error' WHERE id=?", (app_id,))


# ─────────────────────────────────────────────────────────────
# GET /jobs  — danh sách việc làm (public)
# ─────────────────────────────────────────────────────────────
@app.get("/jobs")
def list_jobs(category: str = None):
    jobs = get_all_jobs()
    if category:
        jobs = [j for j in jobs if j["category_slug"] == category]
    categories = sorted({j["category"] for j in jobs})
    return {"total": len(jobs), "categories": categories, "jobs": jobs}


# ─────────────────────────────────────────────────────────────
# GET /jobs/{job_id}  — chi tiết JD (public)
# ─────────────────────────────────────────────────────────────
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    jobs = get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "Không tìm thấy vị trí")
    return {**job, "jd_content": get_jd_content(job_id)}


# ─────────────────────────────────────────────────────────────
# POST /jobs/{job_id}/apply  — ứng viên nộp CV
# ─────────────────────────────────────────────────────────────
@app.post("/jobs/{job_id}/apply")
async def apply_job(
    job_id:     str,
    background: BackgroundTasks,
    name:       str        = Form(...),
    email:      str        = Form(...),
    phone:      str        = Form(""),
    cv_file:    UploadFile = File(...),
):
    jobs = get_all_jobs()
    if not any(j["id"] == job_id for j in jobs):
        raise HTTPException(404, "Không tìm thấy vị trí")

    now    = time.strftime("%Y-%m-%dT%H:%M:%S")
    app_id = "APP-" + uuid.uuid4().hex[:8].upper()

    ext         = Path(cv_file.filename).suffix or ".pdf"
    cv_filename = f"{app_id}{ext}"
    cv_path     = CV_UPLOAD_DIR / cv_filename
    cv_path.write_bytes(await cv_file.read())

    with db() as conn:
        conn.execute(
            """INSERT INTO cv_applications
               (id, job_id, name, email, phone, cv_filename, cv_path, applied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (app_id, job_id, name, email, phone, cv_filename,
             str(cv_path.relative_to(BASE_DIR)), now),
        )

    background.add_task(_do_score_cv, app_id, cv_path, job_id)
    print(f"[Apply] {app_id} | {name} | {job_id}")

    return {"ok": True, "application_id": app_id,
            "message": "CV đã nhận, đang chấm điểm tự động..."}


# ─────────────────────────────────────────────────────────────
# GET /admin/applications  — danh sách ứng viên (admin)
# ─────────────────────────────────────────────────────────────
@app.get("/admin/applications")
def admin_list_applications(
    status:  str = None,
    job_id:  str = None,
    limit:   int = 100,
    _auth=   None,
    x_admin_key: str = Header(None),
):
    require_admin(x_admin_key)
    where, params = [], []
    if status:
        where.append("status = ?");  params.append(status)
    if job_id:
        where.append("job_id = ?");  params.append(job_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM cv_applications {clause} ORDER BY applied_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()

    return {"total": len(rows), "applications": [dict(r) for r in rows]}


# ─────────────────────────────────────────────────────────────
# GET /admin/applications/{id}  — chi tiết 1 ứng viên (admin)
# ─────────────────────────────────────────────────────────────
@app.get("/admin/applications/{app_id}")
def admin_get_application(app_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
    data = dict(row)
    if data.get("score_breakdown"):
        data["score_breakdown"] = json.loads(data["score_breakdown"])
    return data


# ─────────────────────────────────────────────────────────────
# GET /admin/stats  — tổng quan (admin)
# ─────────────────────────────────────────────────────────────
@app.get("/admin/stats")
def admin_stats(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                                      AS total,
                SUM(CASE WHEN status='passed'  THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                ROUND(AVG(CASE WHEN cv_score IS NOT NULL THEN cv_score END), 2) AS avg_score
            FROM cv_applications
        """).fetchone()
    return dict(row)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
