from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import httpx
import logging

from backend.config import THIRD_PARTY_WEBHOOK_URL, require_admin
from backend.services.ai_service import generate_deep_questions

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)

class DeepAnalysisRequest(BaseModel):
    cv_text: str = Field(..., description="Nội dung CV của ứng viên")
    jd_text: str = Field(..., description="Nội dung JD (Mô tả công việc)")
    webhook_url: str = Field(None, description="URL bên thứ 3 để bắn kết quả qua. Nếu trống sẽ dùng config mặc định.")
    n_questions: int = Field(5, description="Số câu hỏi muốn sinh")

async def process_and_send_webhook(req: DeepAnalysisRequest):
    target_url = req.webhook_url or THIRD_PARTY_WEBHOOK_URL
    if not target_url:
        logger.error("Không có webhook_url để bắn dữ liệu.")
        return
        
    try:
        # 1. Generate questions using AI
        questions = await generate_deep_questions(
            cv_text=req.cv_text,
            jd_text=req.jd_text,
            n_questions=req.n_questions
        )
        
        payload = {
            "status": "success",
            "n_questions_requested": req.n_questions,
            "questions": questions
        }
        
        # 2. Send to 3rd party
        async with httpx.AsyncClient() as client:
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
                async with httpx.AsyncClient() as client:
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
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "webhook_url không hợp lệ")
    if req.n_questions < 1 or req.n_questions > 10:
        raise HTTPException(400, "n_questions phải nằm trong khoảng 1-10")
        
    # Process asynchronously to avoid blocking the caller
    bg_tasks.add_task(process_and_send_webhook, req)
    
    return {
        "ok": True,
        "message": f"Đã tiếp nhận yêu cầu sinh {req.n_questions} câu hỏi. Sẽ gửi kết quả tới: {target_url}"
    }
