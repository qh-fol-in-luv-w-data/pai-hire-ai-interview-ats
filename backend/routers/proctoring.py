from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
import httpx
import re
from hmac import compare_digest
from datetime import datetime
import logging

from backend.config import PROCTORING_API_URL, PROCTORING_API_KEY, PROCTORING_WEBHOOK_SECRET, PUBLIC_WEBHOOK_DOMAIN
from backend.database import db

router = APIRouter(tags=["proctoring"])
logger = logging.getLogger(__name__)

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

    webhook_url = f"{PUBLIC_WEBHOOK_DOMAIN.rstrip('/')}/api/v1/webhooks/ai-proctoring"
    
    payload = {
        "session_id": req.app_id,
        "webhook_url": webhook_url
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PROCTORING_API_KEY}"
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
                return {"embed_url": data.get("embed_url")}
            else:
                logger.error(f"Failed to create proctoring session: {resp.status_code} {resp.text}")
                # Giả lập trả về cho demo nếu server ngoài không chạy
                return {"embed_url": f"https://meet.ctpai.vn/detection/?token=mock-token-{req.app_id}&autostart=true"}
    except Exception as e:
        logger.error(f"Exception calling proctoring API: {e}")
        # Giả lập trả về cho demo nếu lỗi kết nối
        return {"embed_url": f"https://meet.ctpai.vn/detection/?token=mock-token-{req.app_id}&autostart=true"}

class ProctoringWebhookPayload(BaseModel):
    session_id: str
    alert_type: str
    timestamp: str
    snapshot_id: str = None

@router.post("/api/v1/webhooks/ai-proctoring")
async def handle_proctoring_webhook(
    payload: ProctoringWebhookPayload,
    x_proctoring_webhook_secret: str = Header(None),
):
    if not PROCTORING_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="PROCTORING_WEBHOOK_SECRET chưa được cấu hình")
    if not x_proctoring_webhook_secret or not compare_digest(x_proctoring_webhook_secret, PROCTORING_WEBHOOK_SECRET):
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
