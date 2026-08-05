from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import hashlib
import hmac
import httpx
import re
import math
from hmac import compare_digest
from datetime import datetime
import logging
from urllib.parse import urlencode, urlparse, urlunparse
import time

from backend.config import (
    ADMIN_KEY,
    PROCTORING_EMBED_PUBLIC_BASE,
    PROCTORING_API_URL,
    PROCTORING_API_KEY,
    PROCTORING_ALERT_THRESHOLD_SECONDS,
    PROCTORING_WEBHOOK_REQUIRE_SECRET,
    PROCTORING_WEBHOOK_SECRET,
    PUBLIC_WEBHOOK_DOMAIN,
)
from backend.database import db

router = APIRouter(tags=["proctoring"])
logger = logging.getLogger(__name__)
ALERT_TOKEN_TTL_SECONDS = 4 * 60 * 60


def _alert_token_secret() -> str:
    secret = PROCTORING_WEBHOOK_SECRET or PROCTORING_API_KEY
    if not secret:
        raise HTTPException(500, "Chưa cấu hình secret cho proctoring alert token")
    return secret


def _sign_alert_token(app_id: str, exp: int) -> str:
    msg = f"{app_id}.{exp}"
    sig = hmac.new(_alert_token_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _verify_alert_token(app_id: str, token: str | None) -> None:
    if not token:
        raise HTTPException(401, "Thiếu proctoring token")
    try:
        exp_raw, sig = token.split(".", 1)
        exp = int(exp_raw)
    except Exception:
        raise HTTPException(401, "Proctoring token không hợp lệ")
    if exp < int(time.time()):
        raise HTTPException(401, "Proctoring token đã hết hạn")
    expected = _sign_alert_token(app_id, exp).split(".", 1)[1]
    if not compare_digest(sig, expected):
        raise HTTPException(401, "Proctoring token không hợp lệ")


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
    ctpai_session_id = f"{req.app_id}:{int(time.time())}"
    session_prefix = f"{req.app_id}:%"
    with db() as conn:
        app = conn.execute("SELECT id FROM cv_applications WHERE id=?", (req.app_id,)).fetchone()
        latest_alert_row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS latest_id FROM proctoring_alerts WHERE session_id=? OR session_id LIKE ?",
            (req.app_id, session_prefix),
        ).fetchone()
    if not app:
        raise HTTPException(404, "Không tìm thấy hồ sơ")
    if not PROCTORING_API_KEY:
        return {"embed_url": None, "mode": "local_webcam", "reason": "PROCTORING_API_KEY chưa được cấu hình"}

    webhook_url = f"{PUBLIC_WEBHOOK_DOMAIN.rstrip('/')}/api/webhooks/ai-proctoring"
    if PROCTORING_WEBHOOK_REQUIRE_SECRET and PROCTORING_WEBHOOK_SECRET:
        webhook_url = f"{webhook_url}?{urlencode({'secret': PROCTORING_WEBHOOK_SECRET})}"
    
    alert_threshold_seconds = PROCTORING_ALERT_THRESHOLD_SECONDS
    if isinstance(alert_threshold_seconds, float) and alert_threshold_seconds.is_integer():
        alert_threshold_seconds = int(alert_threshold_seconds)

    payload = {
        "session_id": ctpai_session_id,
        "webhook_url": webhook_url,
        "alert_threshold_seconds": alert_threshold_seconds,
    }
    parsed_webhook = urlparse(webhook_url)
    logger.info(
        "Creating CTPAI proctoring session session=%s threshold=%s webhook_host=%s webhook_path=%s",
        ctpai_session_id,
        alert_threshold_seconds,
        parsed_webhook.netloc,
        parsed_webhook.path,
    )
    print(
        f"[Proctoring] Create CTPAI session={ctpai_session_id} "
        f"threshold={alert_threshold_seconds} webhook={parsed_webhook.netloc}{parsed_webhook.path}"
    )
    
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
            if resp.status_code == 422 and isinstance(PROCTORING_ALERT_THRESHOLD_SECONDS, float) and not PROCTORING_ALERT_THRESHOLD_SECONDS.is_integer():
                retry_payload = {
                    **payload,
                    "alert_threshold_seconds": math.ceil(PROCTORING_ALERT_THRESHOLD_SECONDS),
                }
                logger.warning(
                    "Proctoring API rejected fractional alert_threshold_seconds=%s; retrying with %s",
                    PROCTORING_ALERT_THRESHOLD_SECONDS,
                    retry_payload["alert_threshold_seconds"],
                )
                resp = await client.post(
                    f"{PROCTORING_API_URL.rstrip('/')}/sessions",
                    json=retry_payload,
                    headers=headers,
                    timeout=10.0
                )
            
            if resp.status_code == 200:
                data = resp.json()
                exp = int(time.time()) + ALERT_TOKEN_TTL_SECONDS
                return {
                    "embed_url": _public_embed_url(data.get("embed_url")),
                    "mode": "ai_proctoring",
                    "alerts_token": _sign_alert_token(req.app_id, exp),
                    "alerts_token_expires_at": exp,
                    "latest_alert_id": int(latest_alert_row["latest_id"] or 0),
                    "proctoring_session_id": ctpai_session_id,
                }
            else:
                logger.error(f"Failed to create proctoring session: {resp.status_code} {resp.text}")
                return {"embed_url": None, "mode": "local_webcam", "reason": "Không kết nối được AI proctoring server"}
    except Exception as e:
        logger.error(f"Exception calling proctoring API: {e}")
        return {"embed_url": None, "mode": "local_webcam", "reason": "Không kết nối được AI proctoring server"}


@router.get("/api/v1/proctoring/alerts")
async def get_proctoring_alerts(app_id: str, last_id: int = 0, token: str = None):
    if not re.fullmatch(r"APP-[A-F0-9]{8}", app_id or ""):
        raise HTTPException(400, "app_id không hợp lệ")
    _verify_alert_token(app_id, token)
    with db() as conn:
        app = conn.execute("SELECT id FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        if not app:
            raise HTTPException(404, "Không tìm thấy hồ sơ")
        rows = conn.execute(
            """
            SELECT id, session_id, alert_type, snapshot_id, timestamp, created_at
            FROM proctoring_alerts
            WHERE (session_id=? OR session_id LIKE ?) AND id>?
            ORDER BY id ASC
            LIMIT 20
            """,
            (app_id, f"{app_id}:%", max(last_id, 0)),
        ).fetchall()
    if rows:
        print(f"[Proctoring] Poll app={app_id} last_id={last_id} -> {len(rows)} alert(s)")
    return {"alerts": [dict(r) for r in rows]}


@router.post("/api/v1/proctoring/debug-alert")
async def debug_proctoring_alert(app_id: str, alert_type: str = "NO_FACE", x_admin_key: str = Header(None)):
    if not ADMIN_KEY or not x_admin_key or not compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(401, "Unauthorized")
    if not re.fullmatch(r"APP-[A-F0-9]{8}", app_id or ""):
        raise HTTPException(400, "app_id không hợp lệ")
    payload = ProctoringWebhookPayload(
        session_id=app_id,
        alert_type=alert_type,
        timestamp=datetime.utcnow().isoformat() + "Z",
        snapshot_id="debug-local",
    )
    return await _handle_proctoring_webhook_payload(payload, PROCTORING_WEBHOOK_SECRET if PROCTORING_WEBHOOK_REQUIRE_SECRET else None)


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
        logger.info("Saved proctoring alert session=%s type=%s snapshot=%s", payload.session_id, payload.alert_type, payload.snapshot_id or "")
        print(f"[Proctoring] Saved alert session={payload.session_id} type={payload.alert_type} snapshot={payload.snapshot_id or '-'}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save proctoring alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/webhooks/ai-proctoring")
@router.post("/webhooks/ai-proctoring")
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
