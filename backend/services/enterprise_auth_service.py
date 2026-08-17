"""Authentication isolated from candidate accounts for enterprise portal."""
from __future__ import annotations
import hashlib
import secrets
import time
from fastapi import Header, HTTPException
from backend.database import db

TTL = 60 * 60 * 24 * 14

def _hash(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()

def create_session(account_id: str) -> str:
    raw = secrets.token_urlsafe(48); now = int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO enterprise_sessions (id,account_id,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)", ("ESE-"+secrets.token_hex(12).upper(),account_id,_hash(raw),now,now+TTL))
    return raw

def current_account(authorization: str | None = Header(None)) -> dict:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ",1)[1].strip()
    if not token: raise HTTPException(401,"Vui lòng đăng nhập tài khoản doanh nghiệp")
    with db() as conn:
        row = conn.execute("""SELECT a.id,a.company_id,a.email,a.status,c.name,c.slug
            FROM enterprise_sessions s JOIN enterprise_accounts a ON a.id=s.account_id
            JOIN companies c ON c.id=a.company_id
            WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND a.status='active' AND c.is_active=1""", (_hash(token),int(time.time()))).fetchone()
    if not row: raise HTTPException(401,"Phiên doanh nghiệp không hợp lệ hoặc tài khoản chưa được duyệt")
    return dict(row)
