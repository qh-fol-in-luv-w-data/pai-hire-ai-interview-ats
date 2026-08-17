"""Server-side sessions and authorization helpers.

Browser clients receive an opaque, random session id.  A user id is never a
credential: all sensitive routes resolve identity from this table instead.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Iterable

from fastapi import Header, HTTPException, Request

from backend.database import db

SESSION_TTL_SECONDS = 60 * 60 * 24 * 14


def _now() -> int:
    return int(time.time())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_session(user_id: str, *, ttl: int = SESSION_TTL_SECONDS) -> str:
    """Create an opaque, revocable session; return the raw value once."""
    raw = secrets.token_urlsafe(48)
    now = _now()
    with db() as conn:
        conn.execute(
            "INSERT INTO user_sessions (id,user_id,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)",
            ("SES-" + secrets.token_hex(12).upper(), user_id, _hash(raw), now, now + ttl),
        )
    return raw


def revoke_session(raw: str | None) -> None:
    if not raw:
        return
    with db() as conn:
        conn.execute("UPDATE user_sessions SET revoked_at=? WHERE token_hash=?", (_now(), _hash(raw)))


def _session_token(request: Request | None, authorization: str | None, legacy: str | None = None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if request:
        cookie = request.cookies.get("pai_session")
        if cookie:
            return cookie
    return (legacy or "").strip()


def current_user(
    request: Request | None = None,
    authorization: str | None = None,
    x_user_id: str | None = None,
    allowed_roles: Iterable[str] | None = None,
) -> dict:
    raw = _session_token(request, authorization, x_user_id)
    if not raw:
        raise HTTPException(401, "Vui lòng đăng nhập lại")
    with db() as conn:
        row = conn.execute(
            """SELECT u.id,u.name,u.email,u.phone,u.role,u.company_id,u.company_status,s.expires_at
                 FROM user_sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?""",
            (_hash(raw), _now()),
        ).fetchone()
        if row:
            conn.execute("UPDATE user_sessions SET last_seen_at=? WHERE token_hash=?", (_now(), _hash(raw)))
    if not row:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    user = dict(row)
    if allowed_roles and user["role"] not in set(allowed_roles):
        raise HTTPException(403, "Bạn không có quyền thực hiện thao tác này")
    return user


def current_user_from_request(
    request: Request,
    authorization: str | None = Header(None),
) -> dict:
    return current_user(request, authorization)


def require_roles(*roles: str):
    def dependency(request: Request, authorization: str | None = Header(None)) -> dict:
        return current_user(request, authorization, allowed_roles=roles)
    return dependency


def is_valid_admin_session(value: str | None) -> bool:
    """Compatibility adapter for legacy X-Admin-Key protected routes.

    The frontend now places an opaque admin session in that header, never the
    platform ADMIN_KEY.  Keeping the header name prevents breaking old routes.
    """
    if not value:
        return False
    try:
        current_user(None, None, value, ("admin", "platform_admin"))
        return True
    except HTTPException:
        return False
