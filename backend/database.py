import sqlite3
from contextlib import contextmanager
from backend.config import DB_PATH

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

        CREATE TABLE IF NOT EXISTS interview_prep (
            id          TEXT PRIMARY KEY,
            app_ref     TEXT,
            position_id TEXT NOT NULL,
            q05_text    TEXT NOT NULL,
            q06_text    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_interviews_candidate ON interviews(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_answers_interview    ON answers(interview_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_job            ON cv_applications(job_id);
        CREATE INDEX IF NOT EXISTS idx_cvapp_status         ON cv_applications(status);
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
        ]:
            try:
                conn.execute(f"ALTER TABLE interviews ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        for col, typedef in [
            ("is_reapplicant", "BOOL DEFAULT 0"),
            ("prev_app_id",    "TEXT"),
            ("level",          "TEXT DEFAULT 'Junior'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE cv_applications ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE interview_prep ADD COLUMN scope TEXT")
        except Exception:
            pass
        # New tables
        conn.executescript("""
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

    print(f"[DB] Sẵn sàng: {DB_PATH}")
