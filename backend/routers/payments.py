"""Verified SePay QR-payment webhook for automatic tenant quota top-ups."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request

from backend.config import SEPAY_ACCOUNT_NUMBER, SEPAY_WEBHOOK_SECRET
from backend.database import db

router = APIRouter(tags=["Payments"])


def _ok(**data):
    # Exact success=true body is required by SePay delivery acknowledgement.
    return {"success": True, **data}


@router.post("/api/webhooks/sepay")
async def sepay_webhook(request: Request):
    if not SEPAY_WEBHOOK_SECRET:
        raise HTTPException(503, "Thanh toán tự động chưa được cấu hình")
    raw_body = await request.body()
    signature = request.headers.get("X-SePay-Signature", "")
    timestamp = request.headers.get("X-SePay-Timestamp", "")
    try:
        issued_at = int(timestamp)
    except ValueError:
        raise HTTPException(401, "Thiếu timestamp SePay")
    if abs(int(time.time()) - issued_at) > 300:
        raise HTTPException(401, "Webhook đã hết hạn")
    expected = "sha256=" + hmac.new(SEPAY_WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Chữ ký SePay không hợp lệ")
    try:
        payload = json.loads(raw_body)
        transaction_id = str(payload["id"])
        amount = int(payload["transferAmount"])
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        raise HTTPException(400, "Dữ liệu giao dịch SePay không hợp lệ")
    if payload.get("transferType") != "in":
        return _ok(ignored="not_incoming")
    # SePay's dashboard test can use a documented/sample account number.
    # Acknowledge it so connectivity tests pass, but never match or credit an
    # order unless an actual payment reaches our configured bank account.
    if SEPAY_ACCOUNT_NUMBER and str(payload.get("accountNumber") or "") != SEPAY_ACCOUNT_NUMBER:
        return _ok(ignored="wrong_account")
    payment_code = str(payload.get("code") or "").strip()
    content = str(payload.get("content") or "")
    with db() as conn:
        # Idempotency: a replayed SePay event must never add quota twice.
        duplicate = conn.execute("SELECT id FROM company_quota_orders WHERE provider='sepay' AND provider_transaction_id=?", (transaction_id,)).fetchone()
        if duplicate:
            return _ok(duplicate=True)
        order = conn.execute("SELECT * FROM company_quota_orders WHERE provider='sepay' AND payment_code=? AND status IN ('pending_payment','payment_submitted')", (payment_code,)).fetchone()
        if not order and content:
            order = conn.execute("SELECT * FROM company_quota_orders WHERE provider='sepay' AND ? LIKE '%' || payment_code || '%' AND status IN ('pending_payment','payment_submitted') ORDER BY created_at DESC LIMIT 1", (content,)).fetchone()
        if not order:
            return _ok(ignored="unmatched_payment")
        if amount != int(order["amount_vnd"]):
            return _ok(ignored="amount_mismatch")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        column = "quota_cv" if order["bucket"] == "cv" else "quota_interview"
        conn.execute(f"UPDATE companies SET {column}=COALESCE({column},0)+? WHERE id=?", (order["units"], order["company_id"]))
        conn.execute("UPDATE company_quota_orders SET status='approved',provider_transaction_id=?,paid_at=?,approved_at=?,approved_by='sepay_webhook' WHERE id=?", (transaction_id, now, now, order["id"]))
    return _ok(order_id=order["id"])
