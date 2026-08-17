"""Shared company quota, idempotency and lightweight audit ledger."""
from __future__ import annotations
import time
import uuid
from fastapi import HTTPException
from backend.database import db

def consume(company_id: str, api_key_id: str | None, *, bucket: str, endpoint: str, request_key: str | None) -> bool:
    """Atomically consume one unit. Return False for an idempotent replay.

    Quota belongs to the company account, shared by every key it creates.
    The internal tenant is unlimited; a newly approved company starts at zero
    and cannot call a paid endpoint until platform admin configures a limit.
    """
    request_key = (request_key or "").strip()
    if request_key and len(request_key) > 128:
        raise HTTPException(422, "Idempotency-Key tối đa 128 ký tự")
    with db() as conn:
        if request_key and conn.execute("SELECT 1 FROM api_usage_ledger WHERE request_key=?", (request_key,)).fetchone():
            return False
        company = conn.execute(f"SELECT quota_{bucket} AS quota FROM companies WHERE id=?", (company_id,)).fetchone()
        if not company:
            raise HTTPException(401, "Công ty không hợp lệ")
        quota = int(company["quota"] or 0)
        used = conn.execute(
            "SELECT COALESCE(SUM(units),0) AS used FROM api_usage_ledger WHERE company_id=? AND endpoint=? AND outcome='charged'",
            (company_id, endpoint),
        ).fetchone()["used"]
        if company_id != "company_default" and quota <= 0:
            raise HTTPException(403, f"Tài khoản chưa được cấp hạn mức {bucket}. Vui lòng liên hệ quản trị viên.")
        if company_id != "company_default" and int(used) >= quota:
            raise HTTPException(429, f"Đã dùng hết quota {bucket}. Vui lòng liên hệ quản trị viên.")
        conn.execute(
            "INSERT INTO api_usage_ledger (id,company_id,api_key_id,request_key,endpoint,units,outcome,created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("USE-" + uuid.uuid4().hex[:16].upper(), company_id, api_key_id, request_key or None, endpoint, 1, "charged", time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
    return True

def usage_summary(company_id: str) -> dict:
    with db() as conn:
        company = conn.execute("SELECT quota_cv,quota_interview FROM companies WHERE id=?", (company_id,)).fetchone()
        rows = conn.execute("SELECT endpoint,COALESCE(SUM(units),0) AS used FROM api_usage_ledger WHERE company_id=? AND outcome='charged' GROUP BY endpoint", (company_id,)).fetchall()
    used = {r["endpoint"]: int(r["used"]) for r in rows}
    def item(quota: int, used_count: int) -> dict:
        unlimited = company_id == "company_default"
        return {"quota": None if unlimited else int(quota or 0), "used": used_count, "remaining": None if unlimited else max(0, int(quota or 0) - used_count)}
    return {"cv": item(int(company["quota_cv"] or 0), used.get("score-cv", 0)), "interview": item(int(company["quota_interview"] or 0), used.get("schedule", 0))}
