from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import httpx
import re
from hmac import compare_digest
from datetime import datetime
import logging
from urllib.parse import urlencode, urlparse, urlunparse

from backend.config import (
    PROCTORING_EMBED_PUBLIC_BASE,
    PROCTORING_API_URL,
    PROCTORING_API_KEY,
    PROCTORING_WEBHOOK_REQUIRE_SECRET,
    PROCTORING_WEBHOOK_SECRET,
    PUBLIC_WEBHOOK_DOMAIN,
)
from backend.database import db

router = APIRouter(tags=["proctoring"])
logger = logging.getLogger(__name__)


def _public_embed_url(embed_url: str | None) -> str | None:
    if not embed_url:
        return None
    parsed = urlparse(embed_url)
    path = parsed.path or "/detection/"
    if parsed.hostname and (
        parsed.hostname.startswith("192.168.")
        or parsed.hostname.startswith("10.")
        or parsed.hostname in {"127.0.0.1", "localhost"}
    ):
        public = urlparse(PROCTORING_EMBED_PUBLIC_BASE)
        parsed = urlparse(urlunparse((
            public.scheme,
            public.netloc,
            public.path or "/detection/",
            "",
            parsed.query,
            "",
        )))
        path = parsed.path or "/detection/"
    if parsed.netloc.endswith("service.ctpai.vn") and path.rstrip("/") == "/detection":
        path = "/detection/camera"
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        "",
        parsed.query,
        "",
    ))


class ProctoringSessionRequest(BaseModel):
    app_id: str

@router.post("/api/v1/proctoring/session")
async def create_proctoring_session(req: ProctoringSessionRequest):
    if not re.fullmatch(r"APP-[A-F0-9]{8}", req.app_id or ""):
        raise HTTPException(400, "app_id không hợp lệ")
    with db() as conn:
        app = conn.execute("SELECT id FROM cv_applications WHERE id=?", (req.app_id,)).fetchone()
    if not app:
        raise HTTPException(404, "Không tìm thấy hồ sơ")
    if not PROCTORING_API_KEY:
        return {"embed_url": None, "mode": "local_webcam", "reason": "PROCTORING_API_KEY chưa được cấu hình"}

    webhook_url = f"{PUBLIC_WEBHOOK_DOMAIN.rstrip('/')}/api/webhooks/ai-proctoring"
    if PROCTORING_WEBHOOK_REQUIRE_SECRET and PROCTORING_WEBHOOK_SECRET:
        webhook_url = f"{webhook_url}?{urlencode({'secret': PROCTORING_WEBHOOK_SECRET})}"
    
    payload = {
        "session_id": req.app_id,
        "webhook_url": webhook_url
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": PROCTORING_API_KEY,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PROCTORING_API_URL.rstrip('/')}/sessions",
                json=payload,
                headers=headers,
                timeout=10.0
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return {"embed_url": _public_embed_url(data.get("embed_url")), "mode": "ai_proctoring"}
            else:
                logger.error(f"Failed to create proctoring session: {resp.status_code} {resp.text}")
                return {"embed_url": None, "mode": "local_webcam", "reason": "Không kết nối được AI proctoring server"}
    except Exception as e:
        logger.error(f"Exception calling proctoring API: {e}")
        return {"embed_url": None, "mode": "local_webcam", "reason": "Không kết nối được AI proctoring server"}


@router.get("/api/v1/proctoring/alerts")
async def get_proctoring_alerts(app_id: str, last_id: int = 0):
    if not re.fullmatch(r"APP-[A-F0-9]{8}", app_id or ""):
        raise HTTPException(400, "app_id không hợp lệ")
    with db() as conn:
        app = conn.execute("SELECT id FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        if not app:
            raise HTTPException(404, "Không tìm thấy hồ sơ")
        rows = conn.execute(
            """
            SELECT id, session_id, alert_type, snapshot_id, timestamp, created_at
            FROM proctoring_alerts
            WHERE session_id=? AND id>?
            ORDER BY id ASC
            LIMIT 20
            """,
            (app_id, max(last_id, 0)),
        ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


class ProctoringWebhookPayload(BaseModel):
    session_id: str
    alert_type: str
    timestamp: str
    snapshot_id: str = None

async def _handle_proctoring_webhook_payload(
    payload: ProctoringWebhookPayload,
    provided_secret: str = None,
):
    if PROCTORING_WEBHOOK_REQUIRE_SECRET:
        if not PROCTORING_WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="PROCTORING_WEBHOOK_SECRET chưa được cấu hình")
        if not provided_secret or not compare_digest(provided_secret, PROCTORING_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", payload.session_id or ""):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", payload.alert_type or ""):
        raise HTTPException(status_code=400, detail="Invalid alert_type")
    try:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO proctoring_alerts (session_id, alert_type, snapshot_id, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.session_id, 
                    payload.alert_type, 
                    payload.snapshot_id, 
                    payload.timestamp, 
                    datetime.utcnow().isoformat()
                )
            )
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save proctoring alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/webhooks/ai-proctoring")
async def handle_proctoring_webhook(
    payload: ProctoringWebhookPayload,
    x_proctoring_webhook_secret: str = Header(None),
    secret: str = None,
):
    return await _handle_proctoring_webhook_payload(payload, x_proctoring_webhook_secret or secret)


@router.post("/api/v1/webhooks/ai-proctoring")
async def handle_proctoring_webhook_v1(
    payload: ProctoringWebhookPayload,
    x_proctoring_webhook_secret: str = Header(None),
    secret: str = None,
):
    return await _handle_proctoring_webhook_payload(payload, x_proctoring_webhook_secret or secret)
