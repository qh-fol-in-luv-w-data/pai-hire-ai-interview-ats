from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import ipaddress
import httpx
import logging
import socket

from backend.config import THIRD_PARTY_WEBHOOK_ALLOWED_HOSTS, THIRD_PARTY_WEBHOOK_URL, require_admin
from backend.services.ai_service import generate_deep_questions

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)

class DeepAnalysisRequest(BaseModel):
    cv_text: str = Field(..., description="Nội dung CV của ứng viên")
    jd_text: str = Field(..., description="Nội dung JD (Mô tả công việc)")
    webhook_url: str = Field(None, description="URL bên thứ 3 để bắn kết quả qua. Nếu trống sẽ dùng config mặc định.")
    n_questions: int = Field(5, description="Số câu hỏi muốn sinh")


def _is_public_ip(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(400, "Không resolve được webhook_url")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_webhook_url(target_url: str) -> str:
    parsed = urlparse(target_url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        raise HTTPException(400, "webhook_url phải là HTTPS hợp lệ")
    hostname = parsed.hostname.lower()
    if THIRD_PARTY_WEBHOOK_ALLOWED_HOSTS and hostname not in THIRD_PARTY_WEBHOOK_ALLOWED_HOSTS:
        raise HTTPException(400, "webhook_url không nằm trong allowlist")
    if not _is_public_ip(hostname):
        raise HTTPException(400, "webhook_url trỏ tới IP nội bộ/không an toàn")
    return target_url

async def process_and_send_webhook(req: DeepAnalysisRequest):
    target_url = validate_webhook_url(req.webhook_url or THIRD_PARTY_WEBHOOK_URL)
    if not target_url:
        logger.error("Không có webhook_url để bắn dữ liệu.")
        return
        
    try:
        # 1. Generate questions using AI
        deep_result = await generate_deep_questions(
            cv_text=req.cv_text,
            jd_text=req.jd_text,
        )
        questions = deep_result.get("questions", [])

        payload = {
            "status": "success",
            "n_questions_requested": req.n_questions,
            "coverage": deep_result.get("coverage"),
            "questions": questions
        }
        
        # 2. Send to 3rd party
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.post(target_url, json=payload, timeout=30.0)
            if resp.status_code >= 400:
                logger.error(f"Lỗi khi gửi webhook tới {target_url}: HTTP {resp.status_code}")
            else:
                logger.info(f"Đã bắn thành công {len(questions)} câu hỏi tới {target_url}")
                
    except Exception as e:
        logger.error(f"Lỗi xử lý webhook Deep Analysis: {e}")
        # In a real system, you might retry or send an error payload to the webhook
        if target_url:
            try:
                async with httpx.AsyncClient(follow_redirects=False) as client:
                    await client.post(target_url, json={"status": "error", "message": str(e)}, timeout=10.0)
            except:
                pass


@router.post("/api/webhook/generate-deep-analysis")
async def handle_generate_deep_analysis(
    req: DeepAnalysisRequest,
    bg_tasks: BackgroundTasks,
    x_admin_key: str = Header(None),
):
    """
    Nhận CV & JD, dùng OpenAI phân tích chuyên sâu (Deep Analysis) 
    để sinh ra bộ câu hỏi phỏng vấn theo kinh nghiệm ứng viên.
    Xử lý bất đồng bộ trong Background Task và bắn kết quả qua webhook_url.
    """
    require_admin(x_admin_key)
    target_url = req.webhook_url or THIRD_PARTY_WEBHOOK_URL
    if not target_url:
        raise HTTPException(400, "Chưa cấu hình THIRD_PARTY_WEBHOOK_URL và cũng không truyền webhook_url trong request.")
    target_url = validate_webhook_url(target_url)
    if req.n_questions < 1 or req.n_questions > 10:
        raise HTTPException(400, "n_questions phải nằm trong khoảng 1-10")
        
    # Process asynchronously to avoid blocking the caller
    bg_tasks.add_task(process_and_send_webhook, req)
    
    return {
        "ok": True,
        "message": f"Đã tiếp nhận yêu cầu sinh {req.n_questions} câu hỏi. Sẽ gửi kết quả tới: {target_url}"
    }
