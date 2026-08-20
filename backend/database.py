import sqlite3
from contextlib import contextmanager
from backend.config import DB_PATH, INTERVIEW_URL, BASE_DIR
import json
import time
from datetime import datetime, timedelta
import os

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

        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            email         TEXT UNIQUE,
            phone         TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            name          TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'candidate',
            created_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

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

        CREATE TABLE IF NOT EXISTS interview_prep (
            id          TEXT PRIMARY KEY,
            app_ref     TEXT,
            position_id TEXT NOT NULL,
            q05_text    TEXT NOT NULL,
            q06_text    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proctoring_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            snapshot_id TEXT,
            timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS application_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT,
            email      TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message    TEXT NOT NULL,
            details    TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_interviews_candidate ON interviews(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_answers_interview    ON answers(interview_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_job            ON cv_applications(job_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_status         ON cv_applications(status);
        CREATE INDEX IF NOT EXISTS idx_proctoring_session   ON proctoring_alerts(session_id);
        CREATE INDEX IF NOT EXISTS idx_app_logs_email       ON application_logs(email);
        CREATE INDEX IF NOT EXISTS idx_app_logs_app         ON application_logs(app_id);
        """)

    # Migration v1: AI evaluation columns
    with db() as conn:
        for col, typedef in [
            ("transcript",     "TEXT"),
            ("ai_level",       "TEXT"),
            ("ai_feedback",    "TEXT"),
            ("question_text",  "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE answers ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE interviews ADD COLUMN prep_id TEXT")
        except Exception:
            pass

    # Migration v2: consent, level, re-interview, HOD questions
    with db() as conn:
        for col, typedef in [
            ("consent_audio",      "BOOL DEFAULT 1"),
            ("consent_camera",     "BOOL DEFAULT 0"),
            ("level",              "TEXT DEFAULT 'Junior'"),
            ("is_reapplicant",     "BOOL DEFAULT 0"),
            ("prev_interview_id",  "TEXT"),
            ("reinterview_of",     "TEXT"),
            ("reinterview_scope",  "TEXT"),
            ("hod_questions",      "TEXT"),
            ("overall_strengths",  "TEXT"),
            ("overall_weaknesses", "TEXT"),
            ("overall_competencies","TEXT"),
            ("video_path",         "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE interviews ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        for col, typedef in [
            ("is_reapplicant", "BOOL DEFAULT 0"),
            ("prev_app_id",    "TEXT"),
            ("level",          "TEXT DEFAULT 'Junior'"),
            ("interview_config", "TEXT"),
            ("prep_status", "TEXT"),
            ("prep_error", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE cv_applications ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE interview_prep ADD COLUMN scope TEXT")
        except Exception:
            pass
        for col, typedef in [
            ("q07_text", "TEXT"),
            ("q08_text", "TEXT"),
            ("generated_questions", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE interview_prep ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        # New tables
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS application_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT,
            email      TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message    TEXT NOT NULL,
            details    TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_app_logs_email ON application_logs(email);
        CREATE INDEX IF NOT EXISTS idx_app_logs_app   ON application_logs(app_id);

        CREATE TABLE IF NOT EXISTS incidents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id TEXT,
            type         TEXT NOT NULL,
            description  TEXT,
            created_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidate_feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT,
            ratings     TEXT,
            nps         INTEGER,
            comments    TEXT,
            created_at  TEXT NOT NULL
        );
        """)

    # Migration v3: § Feature (7) — evaluations table (3 vòng đánh giá)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id       TEXT NOT NULL,
            round        INTEGER NOT NULL,  -- 1=Sơ vấn, 2=Chuyên môn, 3=BOD
            evaluator    TEXT,              -- Tên người chấm
            data         TEXT NOT NULL,     -- JSON: { criteria: [{id, label, score, note}], summary, decision }
            decision     TEXT,              -- 'pass' | 'fail' | 'pending'
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            UNIQUE(app_id, round)
        );
        """)
        # Migration: thêm cột evaluation_status vào cv_applications để track tiến độ 3 vòng
        for col, typedef in [
            ("eval_round1_status", "TEXT"),
            ("eval_round2_status", "TEXT"),
            ("eval_round3_status", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE cv_applications ADD COLUMN {col} {typedef}")
            except Exception:
                pass

    # Migration v4: settings table, tab_switches, time_spent
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        for col, typedef in [
            ("tab_switches", "INTEGER DEFAULT 0")
        ]:
            try:
                conn.execute(f"ALTER TABLE interviews ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        
        for col, typedef in [
            ("time_spent", "INTEGER DEFAULT 0")
        ]:
            try:
                conn.execute(f"ALTER TABLE answers ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE answers ADD COLUMN attempt_number INTEGER DEFAULT 1")
        except Exception:
            pass
        
        # Initialize default settings
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cv_pass_score', '3.0')")

    # Migration v5: interview_slots for link validity
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS interview_slots (
            token       TEXT PRIMARY KEY,
            app_id      TEXT NOT NULL,
            position_id TEXT NOT NULL,
            level       TEXT NOT NULL,
            start_time  TEXT,
            end_time    TEXT,
            created_at  TEXT NOT NULL
        );
        """)

    # Migration v6: CV Score History for stateful tracking
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cv_score_history (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            cv_text TEXT NOT NULL,
            score REAL,
            deep_questions TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cv_score_history_candidate ON cv_score_history(candidate_id);
        """)

    # Migration v7: jobs table
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT,
            jd_text TEXT,
            salary_range TEXT,
            location TEXT,
            work_type TEXT,
            logo_url TEXT,
            is_active INTEGER DEFAULT 1,
            part1_limit INTEGER DEFAULT 11,
            part2_limit INTEGER DEFAULT 7,
            part3_limit INTEGER DEFAULT 5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

    # Migration v8: link phỏng vấn do API cấp và câu hỏi HR chỉnh sửa
    with db() as conn:
        for col, typedef in [
            ("interview_link", "TEXT"),
            ("interview_slot_token", "TEXT"),
            ("interview_link_sent_at", "TEXT"),
            ("interview_link_source", "TEXT"),
            ("cv_extracted_info", "TEXT"),
            ("application_source", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE cv_applications ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE interview_prep ADD COLUMN edited_questions TEXT")
        except Exception:
            pass

        # Backfill legacy API submissions.  They used a generated `jd_` id
        # before application_source existed; keep them in the API tenant queue
        # instead of mixing them with applications submitted on the website.
        try:
            conn.execute("""
                UPDATE cv_applications SET application_source='api'
                WHERE (application_source IS NULL OR application_source='')
                  AND (LOWER(COALESCE(job_id,'')) GLOB 'jd_*'
                       OR EXISTS (SELECT 1 FROM application_logs l
                                  WHERE l.app_id=cv_applications.id
                                    AND l.event_type='application_scored_api'))
            """)
        except Exception:
            pass

        # Dọn CV tạm của luồng API: không có link sau 7 ngày thì xoá.
        try:
            cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
            api_apps = conn.execute("""
                SELECT id, cv_path FROM cv_applications
                WHERE (application_source='api'
                       OR EXISTS (SELECT 1 FROM application_logs l WHERE l.app_id=cv_applications.id AND l.event_type='application_scored_api'))
                  AND cv_path IS NOT NULL AND cv_path != ''
                  AND applied_at < ?
                  AND (interview_link IS NULL OR interview_link='')
            """, (cutoff,)).fetchall()
            for app in api_apps:
                path = BASE_DIR / app['cv_path']
                try:
                    if path.is_file():
                        os.unlink(path)
                except Exception:
                    pass
                conn.execute("UPDATE cv_applications SET cv_path=NULL WHERE id=?", (app['id'],))
        except Exception:
            pass

        # Backfill hồ sơ cũ đã được cấp slot qua API trước khi có các cột mới.
        # Chỉ cập nhật hồ sơ còn ở trạng thái chờ/đã duyệt; không ghi đè tiến
        # độ phỏng vấn đã nộp hoặc đã đánh giá.
        try:
            slots = conn.execute("""
                SELECT s.app_id, s.token, s.created_at
                FROM interview_slots s
                INNER JOIN (
                    SELECT app_id, MAX(created_at) AS latest_created_at
                    FROM interview_slots
                    GROUP BY app_id
                ) latest ON latest.app_id = s.app_id AND latest.latest_created_at = s.created_at
            """).fetchall()
            base = INTERVIEW_URL.rsplit("/interview", 1)[0]
            for slot in slots:
                link = f"{base}/interview?slot={slot['token']}"
                api_sent = conn.execute(
                    "SELECT 1 FROM application_logs WHERE app_id=? AND event_type='application_scored_api' LIMIT 1",
                    (slot['app_id'],),
                ).fetchone()
                source = "api" if api_sent else "admin"
                conn.execute("""
                    UPDATE cv_applications
                    SET interview_link=COALESCE(interview_link, ?),
                        interview_slot_token=COALESCE(interview_slot_token, ?),
                        interview_link_sent_at=COALESCE(interview_link_sent_at, ?),
                        interview_link_source=COALESCE(interview_link_source, ?)
                    WHERE id=?
                """, (link, slot['token'], slot['created_at'], source, slot['app_id']))
                conn.execute("""
                    UPDATE cv_applications
                    SET status='interview_link_sent'
                    WHERE id=?
                      AND status NOT IN ('interview_submitted', 'submitted', 'evaluated', 'passed', 'failed')
                """, (slot['app_id'],))
                if source == "api":
                    conn.execute(
                        "UPDATE cv_applications SET cv_score=NULL, score_breakdown=NULL, ai_summary=NULL WHERE id=?",
                        (slot['app_id'],),
                    )
        except Exception:
            # Không để slot cũ bất thường làm ứng dụng không khởi động.
            pass

        # Bổ sung thông tin trích xuất cho các hồ sơ cũ còn file CV.
        try:
            from backend.services.document_service import extract_cv_text
            from backend.services.cv_extraction import extract_candidate_info
            old_apps = conn.execute(
                "SELECT id, name, email, phone, cv_path FROM cv_applications WHERE cv_path IS NOT NULL AND (cv_extracted_info IS NULL OR cv_extracted_info='')"
            ).fetchall()
            for app in old_apps:
                path = BASE_DIR / app['cv_path']
                if not path.exists():
                    continue
                info = extract_candidate_info(extract_cv_text(path), app['name'], app['email'], app['phone'] or '')
                conn.execute("UPDATE cv_applications SET cv_extracted_info=? WHERE id=?", (json.dumps(info, ensure_ascii=False), app['id']))
        except Exception:
            pass

    # Migration v9: thay mức "Thỏa thuận" bằng khung lương thị trường theo vị trí/cấp bậc.
    with db() as conn:
        try:
            from backend.services.salary_benchmarks import market_salary
            rows = conn.execute("""
                SELECT id, title, category FROM jobs
                WHERE salary_range IS NULL OR TRIM(salary_range)='' OR salary_range LIKE 'Thỏa thuận%'
            """).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE jobs SET salary_range=?, updated_at=? WHERE id=?",
                    (market_salary(row['id'], row['title'], row['category']), time.strftime("%Y-%m-%dT%H:%M:%S"), row['id']),
                )
        except Exception:
            pass

    # Migration v10: đa công ty cho External API. Dữ liệu API luôn thuộc một company_id.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS company_api_keys (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_company_keys_company ON company_api_keys(company_id);
        """)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "INSERT OR IGNORE INTO companies (id, slug, name, is_active, created_at) VALUES (?,?,?,?,?)",
            ("company_default", "pai-internal", "PAI Internal", 1, now),
        )
        for table in ("cv_applications", "interview_slots"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN company_id TEXT")
            except Exception:
                pass
        conn.execute("UPDATE cv_applications SET company_id='company_default' WHERE company_id IS NULL OR company_id='' ")
        try:
            conn.execute("UPDATE interview_slots SET company_id='company_default' WHERE company_id IS NULL OR company_id='' ")
        except Exception:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cvapp_company ON cv_applications(company_id)")
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_company ON interview_slots(company_id)")
        except Exception:
            pass
        for col, typedef in [("company_id", "TEXT"), ("company_status", "TEXT DEFAULT 'active'")]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id)")
        for col, typedef in [("legal_name","TEXT"),("tax_code","TEXT"),("website","TEXT"),("industry","TEXT"),("company_size","TEXT"),("address","TEXT"),("contact_title","TEXT"),("technical_email","TEXT"),("contact_phone","TEXT"),("use_case","TEXT"),("monthly_volume","TEXT"),("privacy_accepted_at","TEXT")]:
            try: conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {typedef}")
            except Exception: pass

    # Migration v11: opaque sessions, tenant data ownership, quota and audit.
    # Kept additive so existing SQLite deployments migrate without data loss.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            last_seen_at INTEGER,
            revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON user_sessions(expires_at);
        CREATE TABLE IF NOT EXISTS api_usage_ledger (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            api_key_id TEXT REFERENCES company_api_keys(id),
            request_key TEXT UNIQUE,
            endpoint TEXT NOT NULL,
            units INTEGER NOT NULL DEFAULT 0,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usage_company ON api_usage_ledger(company_id, created_at);
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            actor_user_id TEXT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS interview_access_sessions (
            id TEXT PRIMARY KEY,
            app_id TEXT NOT NULL,
            slot_token_hash TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            used_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_interview_access_app ON interview_access_sessions(app_id, expires_at);
        CREATE TABLE IF NOT EXISTS company_onboarding_tokens (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            created_at INTEGER NOT NULL
        );
        """)
        for table in ("candidates", "interviews", "answers", "interview_prep", "proctoring_alerts", "application_logs", "candidate_feedback", "incidents"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN company_id TEXT")
            except Exception:
                pass
        for col, typedef in [("quota_cv", "INTEGER NOT NULL DEFAULT 0"), ("quota_interview", "INTEGER NOT NULL DEFAULT 0"), ("quota_reset_at", "TEXT"), ("owner_user_id", "TEXT"), ("approved_at", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        for col, typedef in [("expires_at", "TEXT"), ("scopes", "TEXT DEFAULT 'schedule,read'"), ("last_used_ip", "TEXT"), ("revoked_reason", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE company_api_keys ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        # Existing internal records remain owned by the internal company.
        for table in ("candidates", "interviews", "interview_prep", "application_logs", "candidate_feedback", "incidents"):
            try:
                conn.execute(f"UPDATE {table} SET company_id='company_default' WHERE company_id IS NULL OR company_id='' ")
            except Exception:
                pass

    # Migration v12: one email can be both a candidate and a company admin.
    # Company membership is separate from the user's primary candidate role.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS company_members (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'company_admin',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            approved_at TEXT,
            UNIQUE(company_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_company_members_user ON company_members(user_id, status);
        """)
        # Backfill company-admin users created by an earlier deployment.
        conn.execute("""INSERT OR IGNORE INTO company_members (id,company_id,user_id,role,status,created_at,approved_at)
            SELECT 'MBR-' || lower(hex(randomblob(8))), company_id, id, 'company_admin',
                   CASE WHEN company_status='active' THEN 'active' ELSE 'pending' END,
                   created_at, CASE WHEN company_status='active' THEN created_at ELSE NULL END
            FROM users WHERE company_id IS NOT NULL AND company_id!='' AND role='company_admin'""")

    # Migration v13: enterprise identity is intentionally separate from
    # candidate users, even when both choose the same email address.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS enterprise_accounts (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL UNIQUE REFERENCES companies(id),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            approved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS enterprise_sessions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES enterprise_accounts(id),
            token_hash TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_enterprise_sessions_account ON enterprise_sessions(account_id);
        """)

        # Migration v14: before enterprise accounts were separated, a company
        # administrator was represented by a candidate `users` record plus a
        # `company_members` membership.  Preserve those approved accounts by
        # creating a *separate* enterprise identity once.  The old password
        # hash is copied only as the initial credential; later enterprise
        # sessions are completely isolated from candidate sessions and data.
        #
        # We deliberately use the company's technical email as the identity,
        # so a company receives at most one primary portal login.
        try:
            conn.execute("""
                INSERT OR IGNORE INTO enterprise_accounts
                    (id, company_id, email, password_hash, status, created_at, approved_at)
                SELECT
                    'EAC-' || upper(hex(randomblob(6))),
                    c.id,
                    lower(c.technical_email),
                    u.password_hash,
                    CASE WHEN c.is_active=1 THEN 'active' ELSE 'pending' END,
                    COALESCE(c.created_at, strftime('%Y-%m-%dT%H:%M:%S')),
                    CASE WHEN c.is_active=1 THEN COALESCE(c.approved_at, c.created_at) ELSE NULL END
                FROM companies c
                JOIN company_members m ON m.company_id=c.id
                    AND m.status='active'
                JOIN users u ON u.id=m.user_id
                    AND lower(u.email)=lower(c.technical_email)
                WHERE c.technical_email IS NOT NULL
                  AND trim(c.technical_email)<>''
            """)
        except Exception:
            # Older databases may not yet have all legacy membership columns.
            # Their fresh enterprise registrations remain unaffected.
            pass

    # Migration v15: purchase requests are auditable and require platform
    # approval before any paid quota is credited to a tenant.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS company_quota_orders (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            bucket TEXT NOT NULL CHECK(bucket IN ('cv','interview')),
            units INTEGER NOT NULL,
            unit_price_vnd INTEGER NOT NULL,
            amount_vnd INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_payment',
            created_at TEXT NOT NULL,
            approved_at TEXT,
            approved_by TEXT,
            note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_company_quota_orders_company ON company_quota_orders(company_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_company_quota_orders_status ON company_quota_orders(status, created_at DESC);
        """)

    # Migration v16: passwords are reset with one-time, hashed tokens.  A
    # user and an enterprise account may share an email but remain distinct
    # identities, so the account type is explicitly part of every token.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL CHECK(account_type IN ('user','enterprise')),
            account_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            requested_ip TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_password_reset_account
            ON password_reset_tokens(account_type, account_id, expires_at);
        """)

    # Migration v17: QR payment codes and provider transaction ids make quota
    # crediting idempotent even when a payment webhook is replayed.
    with db() as conn:
        for col, typedef in [
            ("payment_code", "TEXT"), ("provider", "TEXT"),
            ("provider_transaction_id", "TEXT"), ("paid_at", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE company_quota_orders ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_quota_order_payment_code ON company_quota_orders(payment_code) WHERE payment_code IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_quota_order_provider_tx ON company_quota_orders(provider, provider_transaction_id) WHERE provider_transaction_id IS NOT NULL")

    # Migration v18: khung năng lực JD (dùng chung cho bộ đề phỏng vấn và câu hỏi
    # bổ sung qua email) + bộ đề đóng băng tại thời điểm tạo, không dựng lại từ đĩa
    # mỗi lần đọc + câu hỏi đào sâu lưu ở server thay vì chỉ trong localStorage.
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jd_competencies (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            jd_hash TEXT NOT NULL,
            competencies_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, jd_hash)
        );

        CREATE TABLE IF NOT EXISTS interview_follow_ups (
            id            TEXT PRIMARY KEY,
            prep_id       TEXT NOT NULL,
            base_n        TEXT NOT NULL,
            follow_index  INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            audio_path    TEXT,
            transcript    TEXT,
            created_at    TEXT NOT NULL,
            UNIQUE(prep_id, base_n, follow_index)
        );
        CREATE INDEX IF NOT EXISTS idx_follow_ups_prep ON interview_follow_ups(prep_id, base_n);
        """)
        for col, typedef in [
            ("questions_json", "TEXT"),
            ("prep_status", "TEXT"),
            ("prep_error", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE interview_prep ADD COLUMN {col} {typedef}")
            except Exception:
                pass

    print(f"[DB] Sẵn sàng: {DB_PATH}")


def log_application_event(app_id: str | None, email: str | None, event_type: str, message: str, details=None):
    email = (email or "").strip().lower()
    if not email:
        return
    payload = json.dumps(details, ensure_ascii=False) if details is not None else None
    with db() as conn:
        conn.execute(
            "INSERT INTO application_logs (app_id, email, event_type, message, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (app_id, email, event_type, message, payload, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
