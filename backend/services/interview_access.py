"""Capability tokens issued only after a valid interview-slot check."""
from __future__ import annotations
import hashlib
import secrets
import time
from datetime import datetime, timezone
from fastapi import Header, HTTPException
from backend.database import db

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def issue(app_id: str, slot_token: str, expires_at: int) -> str:
    raw = secrets.token_urlsafe(40)
    with db() as conn:
        conn.execute("DELETE FROM interview_access_sessions WHERE expires_at<?", (int(time.time()),))
        conn.execute(
            "INSERT INTO interview_access_sessions (id,app_id,slot_token_hash,token_hash,expires_at,created_at) VALUES (?,?,?,?,?,?)",
            ("IAS-" + secrets.token_hex(10).upper(), app_id, _hash(slot_token), _hash(raw), expires_at, int(time.time())),
        )
    return raw

def require_access(app_id: str | None, x_interview_session: str | None = Header(None)) -> dict | None:
    # Manual CV-upload interview has no scheduled applicant and remains
    # supported. Any application-backed interview must prove this capability.
    if not app_id:
        return None
    if not x_interview_session:
        raise HTTPException(401, "Thiếu phiên phỏng vấn hợp lệ")
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM interview_access_sessions WHERE app_id=? AND token_hash=? AND expires_at>? AND used_at IS NULL",
            (app_id, _hash(x_interview_session), int(time.time())),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Phiên phỏng vấn không hợp lệ hoặc đã hết hạn")
    return dict(row)

def mark_submitted(app_id: str, token: str | None) -> None:
    if not token:
        return
    with db() as conn:
        conn.execute("UPDATE interview_access_sessions SET used_at=? WHERE app_id=? AND token_hash=?", (int(time.time()), app_id, _hash(token)))
