"""Capability tokens for the CV deep-questions reply flow (/candidate/questions,
/candidate/submit_reply). Those routes previously trusted the application id
(`ref`) alone — anyone who saw it (email link, server logs) could read another
candidate's deep-analysis questions or submit a reply on their behalf, directly
affecting that candidate's CV score. Mirrors interview_access.py's pattern: an
opaque, random, single-application, time-limited token, hashed at rest.
"""
from __future__ import annotations
import hashlib
import secrets
import time
from fastapi import HTTPException

from backend.database import db

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days — matches the typical reply deadline


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(app_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Create a fresh access token for this application; return the raw value once."""
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as conn:
        conn.execute("DELETE FROM candidate_reply_access WHERE expires_at<?", (now,))
        conn.execute(
            "INSERT INTO candidate_reply_access (id, app_id, token_hash, expires_at, created_at) VALUES (?,?,?,?,?)",
            ("CRA-" + secrets.token_hex(10).upper(), app_id, _hash(raw), now + ttl, now),
        )
    return raw


def require_access(app_id: str, token: str | None) -> None:
    """Raise 401 unless `token` is a valid, unexpired token issued for app_id."""
    if not token:
        raise HTTPException(401, "Thiếu mã truy cập. Vui lòng dùng đúng đường link trong email.")
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM candidate_reply_access WHERE app_id=? AND token_hash=? AND expires_at>?",
            (app_id, _hash(token), int(time.time())),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Mã truy cập không hợp lệ hoặc đã hết hạn.")
