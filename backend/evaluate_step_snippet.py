import httpx
import uuid
import json
import time
from pathlib import Path
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

TEMP_DIR = BASE_DIR / "outputs" / "temp_pushbacks"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/interview/evaluate-step")
async def evaluate_step(
    audio: UploadFile = File(...),
    question_text: str = Form(...),
    question_type: str = Form(...),
):
    if question_type != "Experience":
        return {"need_pushback": False}

    # 1. Save temp audio
    req_id = uuid.uuid4().hex[:8]
    in_audio_path = TEMP_DIR / f"{req_id}_in.webm"
    in_audio_path.write_bytes(await audio.read())

    # 2. STT via ElevenLabs
    transcript = ""
    try:
        async with httpx.AsyncClient(timeout=30) as hx:
            with open(in_audio_path, "rb") as f:
                r = await hx.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={"xi-api-key": ELEVENLABS_API_KEY},
                    files={"file": (in_audio_path.name, f, "audio/webm")},
                    data={"model_id": "scribe_v2", "language_code": "vi"},
                )
        transcript = r.json().get("text", "").strip()
    except Exception as e:
        print(f"[EvalStep] STT lỗi: {e}")
        return {"need_pushback": False}

    if not transcript or len(transcript.split()) < 5:
        # Nếu quá ngắn, auto hỏi xoáy
        pass

    # 3. LLM GPT-4o
    prompt = f"""Bạn là một chuyên gia phỏng vấn nhân sự khó tính.
Ứng viên vừa trả lời câu hỏi Kinh nghiệm sau: "{question_text}"
Câu trả lời của ứng viên: "{transcript}"

Hãy đánh giá xem câu trả lời này đã đủ sâu sắc, có số liệu thực tế hay giải thích rõ ràng vai trò của họ chưa.
Nếu đã đủ chi tiết, trả về đúng 1 chữ: PASS
Nếu quá sơ sài, chung chung, hoặc thiếu logic, hãy đặt ra ĐÚNG 1 câu hỏi phản biện/xoáy (push-back) thật ngắn gọn, trực diện (dưới 30 từ) để đào sâu hơn. KHÔNG bao gồm các từ như 'PASS' nếu bạn muốn hỏi xoáy.
Chỉ trả về PASS hoặc nội dung câu hỏi phản biện, không giải thích.
"""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100
        )
        ai_resp = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[EvalStep] LLM lỗi: {e}")
        return {"need_pushback": False}

    if ai_resp.upper() == "PASS":
        return {"need_pushback": False, "transcript": transcript}

    # 4. TTS for pushback
    out_audio_name = f"{req_id}_out.mp3"
    out_audio_path = TEMP_DIR / out_audio_name
    try:
        await _tts(ai_resp, out_audio_path)
    except Exception as e:
        print(f"[EvalStep] TTS lỗi: {e}")
        return {"need_pushback": False}

    return {
        "need_pushback": True,
        "pushback_text": ai_resp,
        "pushback_audio": f"/temp_pushbacks/{out_audio_name}"
    }
