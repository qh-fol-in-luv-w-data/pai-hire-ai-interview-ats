import os
import re
import uuid
import time
import json
import httpx
import shutil
import html
import unicodedata
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, File, Form, UploadFile, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from backend.database import db, log_application_event
from backend.services.ai_service import _tts
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, QUESTION_AUDIO_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS, BASE_DIR, LEVEL_ORDER

from backend.services.prep_service import _create_prep, _prep_from_row, normalize_interview_config, follow_up_total_limit, _audio_filename
from backend.services.ai_service import _do_evaluate_interview
from backend.services.ai_service import _tts
from backend.config import OPENAI_API_KEY, ELEVENLABS_API_KEY
from backend.services.email_service import send_pass_email, send_fail_email, send_interview_reminder
from backend.security import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_CV_EXTENSIONS,
    MAX_AUDIO_UPLOAD_BYTES,
    MAX_VIDEO_UPLOAD_BYTES,
    MAX_CV_UPLOAD_BYTES,
    media_content_type_for_path,
    read_upload_limited,
    signed_temp_file_url,
)
from backend.services.interview_access import require_access, mark_submitted
router = APIRouter()


def _report_position_label(value: str | None) -> str:
    raw = str(value or "").strip()
    parenthetical = re.search(r"\(([^)]+)\)", raw)
    label = parenthetical.group(1) if parenthetical else raw
    label = re.sub(r"^(Entry|Junior|Mid|Senior|Manager|Director)[_-]", "", label, flags=re.I)
    label = re.sub(r"[_-]+", " ", label)
    return re.sub(r"\s+", " ", label).strip() or "Chưa xác định"


def _report_level_label(value: str | None, position: str | None) -> str:
    level = str(value or "").strip() or str(position or "").split("_", 1)[0]
    labels = {"Entry": "Thực tập / Mới bắt đầu", "Junior": "Chuyên viên (Junior)", "Mid": "Chuyên viên (Mid-level)", "Senior": "Chuyên viên cao cấp", "Manager": "Quản lý", "Director": "Giám đốc"}
    return labels.get(level, level or "Chưa xác định")


def _report_date_label(value: str | None) -> str:
    if not value:
        return "Chưa có dữ liệu"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%H:%M · %d/%m/%Y")
    except ValueError:
        return str(value)

@router.post("/interview/prep")
async def create_interview_prep(
    background:  BackgroundTasks,
    position_id: str = Form(...),
    app_ref:     str = Form(None),
    level:       str = Form("Junior"),
    force:       bool = Form(False),
    x_interview_session: str = Header(None),
):
    from backend.routers.api_v1 import parse_slot_datetime

    # Check if app_ref has an expired slot
    if app_ref:
        require_access(app_ref, x_interview_session)
        with db() as conn:
            slot = conn.execute("SELECT * FROM interview_slots WHERE app_id=? ORDER BY created_at DESC LIMIT 1", (app_ref,)).fetchone()
            if slot and slot["start_time"] and slot["end_time"]:
                now_utc = datetime.now(timezone.utc)
                try:
                    end_dt = parse_slot_datetime(slot["end_time"])
                    if now_utc > end_dt:
                        raise HTTPException(403, "Khung giờ phỏng vấn đã kết thúc.")
                except HTTPException as e:
                    raise e
                except Exception:
                    pass

    # Nếu app_ref đã có prep sẵn → trả luôn, không gen lại. Prep đang sinh nền
    # (do HR pre-warm qua admin panel, hoặc do một request khác vừa kích hoạt)
    # thì báo generating để candidate poll, tránh gọi CV/LLM/TTS trùng lặp.
    if app_ref and not force:
        with db() as conn:
            existing = conn.execute(
                "SELECT * FROM interview_prep WHERE app_ref=? ORDER BY created_at DESC LIMIT 1",
                (app_ref,)
            ).fetchone()
        if existing:
            existing_status = existing["prep_status"] if "prep_status" in existing.keys() else None
            if existing_status == "generating":
                return {"prep_id": existing["id"], "prep_status": "generating"}
            if existing_status == "error":
                return {"prep_id": existing["id"], "prep_status": "error", "prep_error": existing["prep_error"]}
            print(f"[Prep] Dùng prep sẵn {existing['id']} cho {app_ref}")
            result = _prep_from_row(existing)
            return _merge_follow_ups({**result, "prep_status": "ready"})

    # Chưa có gì dùng được — tạo dòng placeholder rồi sinh nội dung ở background,
    # trả lời ngay cho request thay vì bắt ứng viên chờ suốt quá trình gọi
    # CV/LLM/TTS (có thể mất hàng chục giây tới vài phút).
    new_prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, created_at, prep_status) VALUES (?,?,?,?,?,?,?)",
            (new_prep_id, app_ref, position_id, "", "", now, "generating"),
        )
    from backend.services.prep_service import _run_prep_generation
    background.add_task(_run_prep_generation, new_prep_id, position_id, app_ref, level)
    return {"prep_id": new_prep_id, "prep_status": "generating"}


@router.get("/interview/prep/{prep_id}/status")
async def get_interview_prep_status(
    prep_id: str,
    app_ref: str = None,
    x_interview_session: str = Header(None),
):
    """Candidate poll trạng thái bộ đề đang sinh nền (xem create_interview_prep)."""
    if app_ref:
        require_access(app_ref, x_interview_session)
    with db() as conn:
        row = conn.execute("SELECT * FROM interview_prep WHERE id=?", (prep_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy bộ câu hỏi")
    status = row["prep_status"] if "prep_status" in row.keys() else None
    if status == "generating":
        return {"prep_id": prep_id, "prep_status": "generating"}
    if status == "error":
        return {"prep_id": prep_id, "prep_status": "error", "prep_error": row["prep_error"]}
    result = _prep_from_row(row)
    return _merge_follow_ups({**result, "prep_status": "ready"})


def _merge_follow_ups(result: dict) -> dict:
    """Gộp câu hỏi đào sâu đã sinh và lưu ở server (bảng interview_follow_ups)
    vào bộ câu hỏi trả về, ngay sau câu hỏi gốc của chúng. Server là nguồn sự
    thật cho câu đào sâu — không phải localStorage — nên tải lại trang hay đổi
    thiết bị không làm mất câu đang dở, và một prep_id mới (bộ đề mới) không
    bao giờ vô tình thừa hưởng câu đào sâu của prep cũ vì khoá theo prep_id."""
    prep_id = result.get("prep_id")
    if not prep_id:
        return result
    with db() as conn:
        rows = conn.execute(
            "SELECT base_n, follow_index, question_text, audio_path FROM interview_follow_ups"
            " WHERE prep_id=? ORDER BY base_n, follow_index",
            (prep_id,),
        ).fetchall()
    if not rows:
        return result
    follow_ups_by_base: dict[str, list] = {}
    for r in rows:
        follow_ups_by_base.setdefault(r["base_n"], []).append(r)
    merged = {}
    for n, q in result["questions"].items():
        merged[n] = q
        for r in follow_ups_by_base.get(n, []):
            merged[f"{n}_{r['follow_index']}"] = {
                "text": r["question_text"],
                "audio_url": r["audio_path"],
                "type": "FollowUp",
                "label": "Câu hỏi đào sâu",
                "is_generated": True,
                "allow_follow_up": False,
            }
    result["questions"] = merged
    return result


@router.get("/interview/questions")
def get_questions():
    res = []
    for k, v in QUESTIONS_BANK.items():
        res.append({
            "n": k,
            "type": v["type"],
            "label": v["label"],
            "is_dynamic": v["is_dynamic"],
            "group": v["group"],
            "text": v["text"]
        })
    return {"questions": res}


from pydantic import BaseModel

class AudioGenRequest(BaseModel):
    q_num: str
    app_ref: str = None
    position_id: str = None

@router.post("/interview/generate_audio")
async def generate_audio_for_dynamic_q(req: AudioGenRequest):
    q_data = QUESTIONS_BANK.get(req.q_num)
    if not q_data:
        raise HTTPException(404, "Question not found")
        
    text_template = q_data["text"]
    
    if not q_data["is_dynamic"]:
        # If it's static, just return the static path
        return {"audio_url": f"/audio/q{req.q_num}.mp3", "text": text_template}
        
    # If dynamic, we ideally need to call LLM to fill in the variables using CV/JD.
    # For now, to unblock the flow, we will do a basic string replacement or simple LLM call.
    # We will use a generic replacement until we plug in the real CV text.
    import re
    filled_text = re.sub(r'\[(.*?)\]', r'\1', text_template)
    filled_text = filled_text.replace("số năm", "nhiều")
    
    req_id = uuid.uuid4().hex[:8]
    out_audio_name = f"dyn_{req.q_num}_{req_id}.mp3"
    out_audio_path = TEMP_PUSHBACKS_DIR / out_audio_name
    
    try:
        await _tts(filled_text, out_audio_path)
    except Exception as e:
        print(f"[Generate Audio] TTS error: {e}")
        raise HTTPException(500, "Lỗi tạo audio")
        
    return {
        "audio_url": signed_temp_file_url(out_audio_name),
        "text": filled_text
    }


@router.post("/interview/evaluate-step")
async def evaluate_step(
    audio: UploadFile = File(...),
    question_text: str = Form(...),
    question_type: str = Form(...),
    question_number: str = Form(""),
    history: str = Form("[]"),
    prep_id: str = Form(None),
    reset_follow_ups: bool = Form(False),
    app_ref: str = Form(None),
    x_interview_session: str = Header(None),
):
    from backend.routers.api_v1 import parse_slot_datetime
    if app_ref:
        require_access(app_ref, x_interview_session)
        with db() as conn:
            slot = conn.execute("SELECT * FROM interview_slots WHERE app_id=? ORDER BY created_at DESC LIMIT 1", (app_ref,)).fetchone()
            if slot and slot["start_time"] and slot["end_time"]:
                now_utc = datetime.now(timezone.utc)
                try:
                    end_dt = parse_slot_datetime(slot["end_time"])
                    if now_utc > end_dt:
                        raise HTTPException(403, "Khung giờ phỏng vấn đã kết thúc.")
                except HTTPException as e:
                    raise e
                except Exception:
                    pass
    # 1. Save temp audio
    req_id = uuid.uuid4().hex[:8]
    audio_bytes, audio_ext = await read_upload_limited(
        audio,
        allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        max_bytes=MAX_AUDIO_UPLOAD_BYTES,
        field_name="Audio",
    )
    in_audio_path = TEMP_PUSHBACKS_DIR / f"{req_id}_in{audio_ext}"
    in_audio_path.write_bytes(audio_bytes)

    # 2. STT via ElevenLabs — thử lại tối đa 2 lần khi gặp lỗi tạm thời (429 rate
    # limit hoặc 5xx), vì các câu hỏi liên tiếp trong một buổi phỏng vấn có thể
    # gọi API này dồn dập trong thời gian ngắn.
    transcript = ""
    import httpx
    import asyncio as _asyncio
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as hx:
                with open(in_audio_path, "rb") as f:
                    r = await hx.post(
                        "https://api.elevenlabs.io/v1/speech-to-text",
                        headers={"xi-api-key": ELEVENLABS_API_KEY},
                        files={"file": (in_audio_path.name, f, media_content_type_for_path(in_audio_path))},
                        data={"model_id": "scribe_v2", "language_code": "vi"},
                    )
            if r.status_code >= 400:
                print(f"[Eval] STT HTTP {r.status_code} (lần {attempt + 1}/3): {r.text[:300]}")
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 2:
                        await _asyncio.sleep(1.5 * (attempt + 1))
                        continue
                break
            transcript = r.json().get("text", "").strip()
            break
        except Exception as e:
            print(f"[Eval] STT error (lần {attempt + 1}/3): {e}")
            if attempt < 2:
                await _asyncio.sleep(1.5 * (attempt + 1))
                continue

    question_number = (question_number or "").split("_", 1)[0]

    # Ghi âm lại câu hỏi GỐC: huỷ toàn bộ nhánh đào sâu cũ của câu đó trước khi
    # đánh giá lại — đáp án nền đã đổi thì các câu đào sâu dựa trên đáp án cũ
    # không còn ý nghĩa, và số đếm phải reset về 0 để đánh giá lại từ đầu.
    if reset_follow_ups and prep_id and question_number:
        with db() as conn:
            conn.execute(
                "DELETE FROM interview_follow_ups WHERE prep_id=? AND base_n=?",
                (prep_id, question_number),
            )

    if not transcript:
        return {"need_pushback": False, "transcript": transcript}

    if question_number == "01" or "giới thiệu" in (question_text or "").lower():
        return {"need_pushback": False, "transcript": transcript}

    # Theo yêu cầu: Chỉ follow-up các câu hỏi chuyên môn (Technical) và nghề nghiệp (Experience)
    if question_type not in ["Technical", "Experience"]:
        return {"need_pushback": False, "transcript": transcript}

    # Server là nguồn sự thật cho giới hạn đào sâu — không tin follow_up_limit
    # do client tự tính (client có thể lệch giữa các câu hỏi, hoặc bị sửa).
    # Có 2 trần tách biệt: mỗi câu hỏi, và tổng cả buổi phỏng vấn.
    limits = normalize_interview_config(None)
    if app_ref:
        with db() as conn:
            cfg_row = conn.execute("SELECT interview_config FROM cv_applications WHERE id=?", (app_ref,)).fetchone()
            if cfg_row and cfg_row["interview_config"]:
                try:
                    limits = normalize_interview_config(json.loads(cfg_row["interview_config"]))
                except Exception:
                    pass
    per_question_limit = limits["PART_3_FOLLOW_UP"]
    total_limit = follow_up_total_limit(per_question_limit)

    per_question_count = 0
    total_count = 0
    if prep_id:
        with db() as conn:
            per_question_count = conn.execute(
                "SELECT COUNT(*) c FROM interview_follow_ups WHERE prep_id=? AND base_n=?",
                (prep_id, question_number),
            ).fetchone()["c"]
            total_count = conn.execute(
                "SELECT COUNT(*) c FROM interview_follow_ups WHERE prep_id=?",
                (prep_id,),
            ).fetchone()["c"]

    if per_question_limit <= 0 or per_question_count >= per_question_limit or total_count >= total_limit:
        return {"need_pushback": False, "transcript": transcript}

    # 3. Parse History
    try:
        hist_data = json.loads(history)
    except:
        hist_data = []

    history_text = ""
    for h in hist_data:
        role = "HR" if h.get("role") == "assistant" else "Ứng viên"
        history_text += f"{role}: {h.get('content')}\n"

    # 4. LLM GPT-4o cho Chuẩn hoá và Phản biện
    prompt = f"""Bạn là một chuyên gia phỏng vấn nhân sự nghiêm khắc và kiên nhẫn.
Loại câu hỏi: {question_type}
Câu hỏi ban đầu: "{question_text}"

Dưới đây là lịch sử trao đổi:
{history_text}
Câu trả lời mới nhất của ứng viên (STT thô): "{transcript}"

NHIỆM VỤ CỦA BẠN:
1. Chuẩn hoá đoạn STT thô của câu trả lời mới nhất (sửa lỗi chính tả, bỏ từ thừa như "à", "ừm", giữ nguyên toàn bộ ý chính và phong cách nói của ứng viên).
   - QUAN TRỌNG: Nếu đoạn STT thô có dấu hiệu là ảo giác do nhiễu tạp âm hoặc im lặng (ví dụ: "Tôi tên Nguyễn Văn A", "Cảm ơn các bạn đã theo dõi", "Subtitles by...", hoặc các câu hoàn toàn vô nghĩa không liên quan), hãy trả về chuỗi rỗng "" cho normalized_transcript.
   - TUYỆT ĐỐI KHÔNG TỰ BỊA RA NỘI DUNG MỚI hoặc thay đổi ý nghĩa của ứng viên.

2. Đánh giá câu trả lời và Quyết định follow-up theo hướng khai thác sâu:
   - `follow_up_limit` là giới hạn tối đa. Khi câu trả lời còn thiếu bằng chứng quan trọng, hãy dùng follow-up để kiểm chứng, không PASS quá sớm.
   - TUYỆT ĐỐI trả về "PASS" nếu ứng viên KHÔNG TRẢ LỜI, trả lời QUÁ NGẮN (chỉ "Dạ", "Vâng", "Không biết"), hoặc đoạn STT hoàn toàn vô nghĩa do lỗi ghi âm. Không hỏi follow-up nếu không có thông tin nền tảng gì để đào sâu.
   - Với câu trả lời có nội dung nhưng còn thiếu 1 trong các điểm sau, ưu tiên hỏi follow-up: ví dụ/case cụ thể, vai trò cá nhân, số liệu/kết quả, công cụ/hệ thống đã dùng, cách kiểm soát rủi ro/sai sót, nguyên nhân gốc rễ, bài học hoặc tác động tới doanh nghiệp.
   - Nếu ứng viên kể chung chung theo kiểu "tôi phụ trách/quản lý/theo dõi/phối hợp" nhưng chưa nói làm thế nào, đo bằng gì, kết quả ra sao, hãy hỏi đào sâu.
   - Nếu câu trả lời đã có ví dụ và kết quả nhưng thiếu số liệu hoặc thiếu phần ứng viên trực tiếp làm, vẫn nên hỏi 1 follow-up để xác minh.
   - Chỉ PASS khi câu trả lời đã đủ rõ để đánh giá khắt khe: có bối cảnh, hành động cá nhân, phương pháp, minh chứng và kết quả hoặc giới hạn/rủi ro.

3. Nếu thật sự cần hỏi follow-up, câu hỏi phải:
   - Ngắn gọn (dưới 30 từ), trực tiếp, không có câu mở đầu xã giao.
   - Chỉ hỏi 1 khía cạnh còn yếu nhất, ưu tiên: số liệu/kết quả, vai trò cá nhân, nguyên nhân gốc rễ, công cụ/hệ thống, hoặc kiểm soát rủi ro.
   - Yêu cầu ứng viên trả lời bằng ví dụ thật, con số, quyết định cụ thể hoặc tình huống thực tế.
   - Bắt đầu bằng: "Cụ thể hơn...", "Con số/kết quả cụ thể là gì?", "Bạn trực tiếp làm phần nào?", "Bạn kiểm soát rủi ro đó ra sao?" v.v.

BẮT BUỘC trả về định dạng JSON hợp lệ (không kèm theo block code markdown), gồm 4 field:
{{
  "normalized_transcript": "<đoạn STT đã chuẩn hoá>",
  "khia_canh_can_khai_thac": ["khía cạnh 1", "khía cạnh 2"],
  "danh_muc_cau_hoi_follow_up": ["câu 1", "câu 2"],
  "pushback_question": "<1 câu hỏi phản biện duy nhất hoặc 'PASS'>"
}}
"""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        ai_resp_raw = resp.choices[0].message.content
        print(f"[EvalStep] LLM response received | q={question_number or '-'} | chars={len(ai_resp_raw or '')}")
        
        try:
            ai_data = json.loads(ai_resp_raw)
            norm_transcript = ai_data.get("normalized_transcript", transcript)
            ai_resp = ai_data.get("pushback_question", "PASS")
        except:
            norm_transcript = transcript
            ai_resp = "PASS"
    except Exception as e:
        print(f"[EvalStep] LLM lỗi: {e}")
        return {"need_pushback": False, "transcript": transcript}

    transcript = norm_transcript

    # Nếu sau khi chuẩn hoá (loại bỏ ảo giác STT) mà transcript rỗng, thì bỏ qua không hỏi xoáy
    # để tránh vòng lặp hỏi lại khi ứng viên im lặng
    if not transcript.strip():
        return {"need_pushback": False, "transcript": transcript}

    if ai_resp.strip().upper() == "PASS":
        return {"need_pushback": False, "transcript": transcript}

    # 5. TTS for pushback — lưu bền theo hash nội dung dưới route /audio/ tĩnh,
    # không dùng URL tạm có hạn (TEMP_PUSHBACKS_DIR bị dọn hoặc chữ ký hết hạn
    # thì audio câu đào sâu chết lặng khi ứng viên tải lại trang).
    out_audio_name = _audio_filename(ai_resp)
    out_audio_path = QUESTION_AUDIO_DIR / out_audio_name
    try:
        await _tts(ai_resp, out_audio_path)
    except Exception as e:
        print(f"[EvalStep] TTS lỗi: {e}")
        return {"need_pushback": False, "transcript": transcript}

    follow_index = per_question_count + 1
    pushback_audio_url = f"/audio/{out_audio_name}"
    if prep_id:
        with db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO interview_follow_ups"
                " (id, prep_id, base_n, follow_index, question_text, audio_path, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    f"FU-{uuid.uuid4().hex[:10].upper()}", prep_id, question_number,
                    follow_index, ai_resp, pushback_audio_url,
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                ),
            )

    return {
        "need_pushback": True,
        "pushback_text": ai_resp,
        "pushback_audio": pushback_audio_url,
        "pushback_n": f"{question_number}_{follow_index}",
        "transcript": transcript
    }


@router.post("/interview/submit")
async def submit_interview(
    background:   BackgroundTasks,
    request:      Request,
):
    form = await request.form()
    position_id = form.get("position_id")
    candidate_id = form.get("candidate_id")
    app_ref      = form.get("app_ref")
    x_interview_session = request.headers.get("x-interview-session")
    prep_id      = form.get("prep_id")
    level        = form.get("level", "Junior")
    reiv         = form.get("reiv")
    cv_file      = form.get("cv_file")
    
    from backend.routers.api_v1 import parse_slot_datetime
    if app_ref:
        require_access(app_ref, x_interview_session)
        with db() as conn:
            slot = conn.execute("SELECT * FROM interview_slots WHERE app_id=? ORDER BY created_at DESC LIMIT 1", (app_ref,)).fetchone()
            if slot and slot["start_time"] and slot["end_time"]:
                now_utc = datetime.now(timezone.utc)
                try:
                    end_dt = parse_slot_datetime(slot["end_time"])
                    if now_utc > end_dt:
                        raise HTTPException(403, "Khung giờ phỏng vấn đã kết thúc, không thể nộp bài.")
                except HTTPException as e:
                    raise e
                except Exception:
                    pass
    tab_switches = int(form.get("tab_switches", 0) or 0)
    time_spent_raw = form.get("time_spent", "{}")
    try:
        time_spent = json.loads(time_spent_raw)
    except:
        time_spent = {}

    pushback_texts_raw = form.get("pushback_texts", "{}")
    try:
        pushback_texts = json.loads(pushback_texts_raw)
    except:
        pushback_texts = {}

    answer_transcripts_raw = form.get("answer_transcripts", "{}")
    try:
        answer_transcripts = json.loads(answer_transcripts_raw)
    except:
        answer_transcripts = {}

    question_meta_raw = form.get("question_meta", "{}")
    try:
        question_meta = json.loads(question_meta_raw)
    except:
        question_meta = {}
    
    if not position_id:
        raise HTTPException(400, "Thiếu position_id")

    now          = time.strftime("%Y-%m-%dT%H:%M:%S")
    interview_id = "IV-" + uuid.uuid4().hex[:10].upper()
    session_dir  = OUTPUT_DIR / interview_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Tạo candidate nếu chưa có
    if not candidate_id:
        candidate_id = "C-" + uuid.uuid4().hex[:8].upper()

    cv_filename = "cv_unknown.pdf"
    c_name = f"Unknown_{candidate_id[-4:]}"
    c_email = None
    if isinstance(cv_file, UploadFile) and hasattr(cv_file, "filename") and cv_file.filename:
        cv_bytes, cv_ext = await read_upload_limited(
            cv_file,
            allowed_extensions=ALLOWED_CV_EXTENSIONS,
            max_bytes=MAX_CV_UPLOAD_BYTES,
            field_name="CV",
        )
        cv_filename = f"cv{cv_ext}"
        cv_path     = session_dir / cv_filename
        cv_path.write_bytes(cv_bytes)
    elif app_ref:
        # Dùng CV từ application đã nộp
        with db() as conn:
            row = conn.execute(
                "SELECT cv_path, name, email FROM cv_applications WHERE id=?", (app_ref,)
            ).fetchone()
        if row:
            c_name  = row["name"]
            c_email = row["email"]
            if row["cv_path"]:
                src = BASE_DIR / row["cv_path"]
                cv_filename = src.name
                cv_path     = session_dir / cv_filename
                import shutil; shutil.copy2(str(src), str(cv_path))
            else:
                cv_filename = "cv_unknown.pdf"
                cv_path     = session_dir / cv_filename
                cv_path.write_bytes(b"")
    else:
        raise HTTPException(400, "Cần upload CV hoặc cung cấp app_ref")
    full_video = form.get("full_video")
    video_path_str = None
    if isinstance(full_video, UploadFile) and hasattr(full_video, "filename") and full_video.filename:
        video_bytes, _ = await read_upload_limited(
            full_video,
            allowed_extensions={".webm"},
            max_bytes=MAX_VIDEO_UPLOAD_BYTES,
            field_name="Video phỏng vấn",
        )
        video_path = session_dir / "full_video.webm"
        video_path.write_bytes(video_bytes)
        video_path_str = str(video_path.relative_to(BASE_DIR))

        # Upload video phỏng vấn lên MinIO Storage theo candidate_id & tên ứng viên
        try:
            from backend.services.storage_service import upload_video_to_minio
            import unicodedata, re

            # Chuẩn hóa tên ứng viên (bỏ dấu tiếng Việt & ký tự đặc biệt) để tạo key an toàn trên MinIO
            raw_name = c_name or "Candidate"
            nfkd = unicodedata.normalize('NFKD', raw_name)
            clean_name = ''.join([c for c in nfkd if not unicodedata.combining(c)])
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)
            clean_name = re.sub(r'_+', '_', clean_name).strip('_') or "Candidate"

            minio_object_key = f"candidates/{candidate_id}_{clean_name}/{interview_id}_{clean_name}_full_video.webm"
            minio_url = upload_video_to_minio(video_bytes, minio_object_key, content_type="video/webm")
            if minio_url:
                print(f"[Interview] Đã lưu video phỏng vấn của ứng viên {c_name} ({candidate_id}) lên MinIO Storage: {minio_url}")
        except Exception as err:
            print(f"[Interview] Lỗi upload video lên MinIO: {err}")

    answer_rows = []
    # Lưu các audio tải lên (hỗ trợ động mọi số lượng câu hỏi)
    for key, upload in form.multi_items():
        if key.startswith("answer_") and hasattr(upload, "filename"):
            qn_raw = key.replace("answer_", "") # VD: "07", "05_1"
            
            if "_" in qn_raw:
                qn, sub = qn_raw.split("_", 1)
                question_number = f"{qn}.{sub}"
            else:
                qn = qn_raw
                question_number = qn

            q_meta = {}
            if isinstance(question_meta, dict):
                q_meta = question_meta.get(qn_raw) or question_meta.get(qn) or {}
            original_qn = str(q_meta.get("original_n") or qn).split("_", 1)[0]
            q_type = q_meta.get("type") or QUESTIONS_BANK.get(original_qn, {}).get("type", "General")
            if q_type == "FollowUp":
                q_type = QUESTIONS_BANK.get(original_qn, {}).get("type", "Technical")

            audio_bytes, audio_ext = await read_upload_limited(
                upload,
                allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
                max_bytes=MAX_AUDIO_UPLOAD_BYTES,
                field_name="Audio",
            )
            audio_name = f"{key}{audio_ext}"
            audio_path = session_dir / audio_name
            audio_path.write_bytes(audio_bytes)
            
            q_text = pushback_texts.get(key.replace("answer_", ""), None)
            if q_text is None:
                q_text = q_meta.get("text")
            if not q_text and "_" in qn_raw:
                q_text = f"Câu hỏi đào sâu cho câu {qn}"
            transcript_text = ""
            if isinstance(answer_transcripts, dict):
                transcript_text = str(answer_transcripts.get(qn_raw) or answer_transcripts.get(qn) or "").strip()

            answer_rows.append({
                "interview_id":    interview_id,
                "question_number": question_number,
                "question_type":   q_type,
                "question_text":   q_text,
                "transcript":      transcript_text,
                "audio_path":      str(audio_path.relative_to(BASE_DIR)),
                "created_at":      now,
                "attempt_number":  1,
            })


    # ── Re-interview: lưu thêm vào interview GỐC, không tạo mới ──
    if reiv:
        with db() as conn:
            orig = conn.execute(
                "SELECT id, candidate_id, position_id FROM interviews WHERE id=?", (reiv,)
            ).fetchone()
            if not orig:
                raise HTTPException(404, f"Không tìm thấy interview gốc: {reiv}")

            attempt_row = conn.execute(
                "SELECT COALESCE(MAX(attempt_number), 1) AS max_attempt FROM answers WHERE interview_id=?",
                (reiv,),
            ).fetchone()
            next_attempt = int(attempt_row["max_attempt"] or 1) + 1

            # Chèn answers mới vào interview gốc (giữ nguyên answers cũ để HR so sánh)
            reiv_rows = [{**r, "interview_id": reiv, "attempt_number": next_attempt} for r in answer_rows]
            conn.executemany("""
                INSERT INTO answers
                    (interview_id, question_number, question_type, question_text, transcript, audio_path, created_at, time_spent, attempt_number)
                VALUES (:interview_id, :question_number, :question_type, :question_text, :transcript, :audio_path, :created_at, :time_spent, :attempt_number)
            """, [{**r, "time_spent": time_spent.get(r["question_number"].split(".")[0], 0)} for r in reiv_rows])


            # Cập nhật interview gốc
            conn.execute(
                "UPDATE interviews SET status='submitted', submitted_at=?, prep_id=COALESCE(?, prep_id), video_path=COALESCE(?, video_path) WHERE id=?",
                (now, prep_id or None, video_path_str, reiv),
            )

        print(f"[✓] Re-interview {reiv} | attempt={next_attempt} | {len(answer_rows)} answers added")
        if c_email:
            log_application_event(
                app_ref,
                c_email,
                "reinterview_submitted",
                f"Ứng viên đã nộp bài phỏng vấn lại cho {reiv}.",
                {"interview_id": reiv, "attempt_number": next_attempt, "answers_saved": len(answer_rows)},
            )
        background.add_task(_do_evaluate_interview, reiv, position_id, reiv_rows)
        if app_ref:
            mark_submitted(app_ref, x_interview_session)
        return {"ok": True, "interview_id": reiv, "reinterview": True, "attempt_number": next_attempt, "answers_saved": len(answer_rows)}

    # ── Phỏng vấn mới: flow thông thường ───────────────────────
    with db() as conn:
        conn.execute("""
            INSERT INTO candidates (id, name, email, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name  = COALESCE(excluded.name,  candidates.name),
                email = COALESCE(excluded.email, candidates.email)
        """, (candidate_id, c_name, c_email, now))

        conn.execute("""
            INSERT INTO interviews
                (id, candidate_id, position_id, cv_filename, cv_path, prep_id, level, submitted_at, tab_switches, status, reinterview_scope, video_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interview_id, candidate_id, position_id,
            cv_filename, str(cv_path.relative_to(BASE_DIR)), prep_id, level, now, tab_switches, "submitted", '[]', video_path_str
        ))


        conn.executemany("""
            INSERT INTO answers
                (interview_id, question_number, question_type, question_text, transcript, audio_path, created_at, time_spent, attempt_number)
            VALUES (:interview_id, :question_number, :question_type, :question_text, :transcript, :audio_path, :created_at, :time_spent, :attempt_number)
        """, [{**r, "time_spent": time_spent.get(r["question_number"].split(".")[0], 0)} for r in answer_rows])

    if app_ref:
        mark_submitted(app_ref, x_interview_session)
    print(f"[✓] {interview_id} | candidate={candidate_id} | position={position_id}")
    if c_email:
        log_application_event(
            app_ref,
            c_email,
            "interview_submitted",
            f"Ứng viên đã nộp bài phỏng vấn {interview_id}.",
            {"interview_id": interview_id, "answers_saved": len(answer_rows), "position_id": position_id},
        )
    background.add_task(_do_evaluate_interview, interview_id, position_id, answer_rows)

    return {
        "ok":            True,
        "interview_id":  interview_id,
        "candidate_id":  candidate_id,
        "answers_saved": len(answer_rows),
    }


@router.get("/interview/{interview_id}")
def get_interview(interview_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute("""
            SELECT i.*, c.name as candidate_name, ca.application_source
            FROM interviews i
            LEFT JOIN candidates c ON i.candidate_id = c.id
            LEFT JOIN interview_prep ip ON ip.id = i.prep_id
            LEFT JOIN cv_applications ca ON ca.id = ip.app_ref
            WHERE i.id = ?
        """, (interview_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy interview")

        answers = conn.execute(
            "SELECT * FROM answers WHERE interview_id = ? ORDER BY attempt_number, question_number",
            (interview_id,)
        ).fetchall()

    return {
        **dict(row),
        "answers": [dict(a) for a in answers],
    }


@router.get("/candidate/{candidate_id}/interviews")
def get_candidate_interviews(candidate_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        candidate = conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if not candidate:
            raise HTTPException(404, "Không tìm thấy candidate")

        interviews = conn.execute("""
            SELECT i.id, i.position_id, i.status, i.submitted_at,
                   COUNT(a.id) as answer_count
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            WHERE i.candidate_id = ?
            GROUP BY i.id
            ORDER BY i.submitted_at DESC
        """, (candidate_id,)).fetchall()

    return {
        "candidate_id": candidate_id,
        "total":        len(interviews),
        "interviews":   [dict(r) for r in interviews],
    }


@router.get("/interviews")
def list_interviews(status: str = None, position_id: str = None, limit: int = 50, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    where, params = [], []
    if status:
        where.append("i.status = ?");      params.append(status)
    if position_id:
        where.append("i.position_id = ?"); params.append(position_id)

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(f"""
            SELECT i.id, i.candidate_id, i.position_id,
                   i.status, i.submitted_at,
                   c.name as candidate_name,
                   COUNT(a.id) as answer_count,
                   (
                     SELECT ROUND(AVG(group_score), 1)
                     FROM (
                       SELECT AVG(CASE ax.ai_level
                         WHEN 'nắm vững'    THEN 10.0
                         WHEN 'am hiểu'     THEN 7.5
                         WHEN 'có biết qua' THEN 5.0
                         WHEN 'không biết'  THEN 0.0
                         ELSE NULL END) AS group_score
                       FROM answers ax
                       WHERE ax.interview_id = i.id
                       GROUP BY ax.attempt_number,
                         CASE
                           WHEN instr(ax.question_number, '.') > 0 THEN substr(ax.question_number, 1, instr(ax.question_number, '.') - 1)
                           ELSE ax.question_number
                         END
                     )
                   ) as avg_score
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            {clause}
            GROUP BY i.id
            ORDER BY i.submitted_at DESC
            LIMIT ?
        """, (*params, limit)).fetchall()

    return {"total": len(rows), "interviews": [dict(r) for r in rows]}


@router.post("/interview/{interview_id}/evaluate")
async def trigger_evaluate(interview_id: str, background: BackgroundTasks,
                           x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        iv = conn.execute("SELECT * FROM interviews WHERE id=?", (interview_id,)).fetchone()
        if not iv:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        rows = conn.execute(
            # Lấy tất cả answers — _do_evaluate_interview tự deduplicate theo created_at
            "SELECT interview_id, question_number, question_type, question_text, transcript, audio_path, created_at, attempt_number FROM answers WHERE interview_id=? ORDER BY attempt_number, created_at",
            (interview_id,)
        ).fetchall()
    answer_rows = [dict(r) for r in rows]
    background.add_task(_do_evaluate_interview, interview_id, iv["position_id"], answer_rows)
    return {"ok": True, "message": f"Đang đánh giá {interview_id}, kết quả sẽ sẵn sàng sau ~1 phút."}


@router.get("/interview/{interview_id}/report")
def interview_report(interview_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        iv = conn.execute(
            "SELECT i.*, c.name as candidate_name FROM interviews i LEFT JOIN candidates c ON i.candidate_id = c.id WHERE i.id=?", (interview_id,)
        ).fetchone()
        if not iv:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")

        answers = conn.execute(
            "SELECT * FROM answers WHERE interview_id=? ORDER BY attempt_number, question_number",
            (interview_id,)
        ).fetchall()

    rows = [dict(a) for a in answers]

    # Avg score: follow-up chỉ nâng điểm khi nó cao hơn câu gốc.
    grouped_scores = {}
    scored_levels = []
    for r in rows:
        level = r["ai_level"]
        if not level or level not in LEVEL_ORDER:
            continue
        base_qn = str(r["question_number"] or "").split(".", 1)[0]
        group_key = f"{r.get('attempt_number', 1)}:{base_qn}"
        score = LEVEL_ORDER[level]
        group = grouped_scores.setdefault(group_key, {"base_score": None, "follow_up_scores": [], "levels": []})
        if "." in str(r["question_number"] or ""):
            group["follow_up_scores"].append(score)
        else:
            group["base_score"] = score
        group["levels"].append(level)

    scores = []
    for item in grouped_scores.values():
        base_score = item["base_score"]
        if base_score is None:
            included_scores = item["follow_up_scores"]
        else:
            included_scores = [base_score, *(value for value in item["follow_up_scores"] if value > base_score)]
        if included_scores:
            scores.append(sum(included_scores) / len(included_scores))
    scored_levels = [level for item in grouped_scores.values() for level in item["levels"]]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    summary   = {l: scored_levels.count(l) for l in LEVEL_ORDER}

    groups = {}
    for r in rows:
        qt = r["question_type"] or "Unknown"
        if qt == "FollowUp":
            qt = "Technical"
        groups.setdefault(qt, []).append(r)

    return {
        "interview_id":   interview_id,
        "candidate_name": iv["candidate_name"],
        "position":       iv["position_id"],
        "level":          iv["level"],
        "status":         iv["status"],
        "submitted_at":   iv["submitted_at"],
        "avg_score":      avg_score,
        "summary":        summary,
        "overall_strengths": iv["overall_strengths"],
        "overall_weaknesses": iv["overall_weaknesses"],
        "overall_competencies": iv["overall_competencies"],
        "groups":         groups,
        "answers":        rows,
    }


@router.get("/interview/{interview_id}/report.pdf")
def download_interview_report_pdf(interview_id: str, x_admin_key: str = Header(None)):
    """Generate a searchable, Unicode-safe PDF rather than a browser screenshot."""
    report = interview_report(interview_id, x_admin_key)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        raise HTTPException(503, "Chưa cài bộ tạo PDF. Hãy build lại Docker.") from error

    font_dir = "/usr/share/fonts/truetype/dejavu"
    pdfmetrics.registerFont(TTFont("DejaVu", f"{font_dir}/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", f"{font_dir}/DejaVuSans-Bold.ttf"))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("InterviewTitle", parent=styles["Title"], fontName="DejaVu-Bold", fontSize=20, leading=25, textColor=colors.white, spaceAfter=4)
    subtitle = ParagraphStyle("InterviewSubtitle", parent=styles["Normal"], fontName="DejaVu", fontSize=9, leading=13, textColor=colors.HexColor("#C7D9F1"))
    heading = ParagraphStyle("InterviewHeading", parent=styles["Heading2"], fontName="DejaVu-Bold", fontSize=13, leading=17, textColor=colors.HexColor("#102A4C"), spaceBefore=12, spaceAfter=6)
    question = ParagraphStyle("InterviewQuestion", parent=styles["Normal"], fontName="DejaVu-Bold", fontSize=10, leading=14, textColor=colors.HexColor("#172033"), spaceBefore=5, spaceAfter=4)
    body = ParagraphStyle("InterviewBody", parent=styles["BodyText"], fontName="DejaVu", fontSize=9, leading=14, textColor=colors.HexColor("#334155"))
    small = ParagraphStyle("InterviewSmall", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#52657B"))
    white_small = ParagraphStyle("InterviewWhiteSmall", parent=small, textColor=colors.HexColor("#C7D9F1"))
    score_style = ParagraphStyle("InterviewScore", parent=question, fontName="DejaVu-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#0F5CC0"))

    def paragraph_text(value):
        return html.escape(str(value or "")).replace("\n", "<br/>")

    def score_label(value):
        return "Chưa chấm" if value is None else f"{value:.1f}/10"

    score_map = {"nắm vững": 10.0, "am hiểu": 7.5, "có biết qua": 5.0, "không biết": 0.0}
    groups = {}
    for answer in report["answers"]:
        question_number = str(answer.get("question_number") or "")
        base_number = question_number.split(".", 1)[0]
        key = (answer.get("attempt_number") or 1, base_number)
        group = groups.setdefault(key, {"attempt": key[0], "number": base_number, "answers": [], "base_score": None, "follow_up_scores": []})
        group["answers"].append(answer)
        value = score_map.get(answer.get("ai_level"))
        if value is not None:
            if "." in question_number:
                group["follow_up_scores"].append(value)
            else:
                group["base_score"] = value
    for group in groups.values():
        base_score = group["base_score"]
        included = group["follow_up_scores"] if base_score is None else [base_score, *(value for value in group["follow_up_scores"] if value > base_score)]
        group["score"] = sum(included) / len(included) if included else None

    competency_labels = {"Technical": "Chuyên môn", "Experience": "Kinh nghiệm", "General": "Tổng quát", "Situational": "Xử lý tình huống", "Behavioral": "Hành vi"}
    competency_scores = {}
    for group in groups.values():
        root = next((answer for answer in group["answers"] if "." not in str(answer.get("question_number") or "")), None)
        category = competency_labels.get((root or {}).get("question_type") or "General", "Tổng quát")
        if group["score"] is not None:
            competency_scores.setdefault(category, []).append(group["score"])
    competency_profile = [(label, sum(values) / len(values)) for label, values in competency_scores.items()]
    if not competency_profile and report.get("avg_score") is not None:
        competency_profile = [("Đánh giá tổng hợp", report["avg_score"])]

    candidate_name = report.get("candidate_name") or "Ứng viên"
    position_label = _report_position_label(report.get("position"))
    level_label = _report_level_label(report.get("level"), report.get("position"))
    submitted_label = _report_date_label(report.get("submitted_at"))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=f"Báo cáo phỏng vấn - {candidate_name}")
    status_labels = {"submitted": "Đã nộp", "evaluated": "Đã đánh giá", "passed": "Đạt", "failed": "Không đạt", "reviewed": "Đã duyệt"}
    average = report.get("avg_score")
    if average is None:
        recommendation = "Chưa đủ dữ liệu đánh giá"
    elif average >= 8.5:
        recommendation = "Khuyến nghị cao"
    elif average >= 7:
        recommendation = "Khuyến nghị xem xét"
    elif average >= 5:
        recommendation = "Cần phỏng vấn bổ sung"
    else:
        recommendation = "Chưa khuyến nghị"

    header = Table([[Paragraph("PAI HIRE", white_small), Paragraph("BÁO CÁO ĐÁNH GIÁ PHỎNG VẤN", white_small)], [Paragraph(paragraph_text(candidate_name), title), ""], [Paragraph(paragraph_text(f"Vị trí ứng tuyển: {position_label}"), subtitle), Paragraph(paragraph_text(f"Hoàn thành: {submitted_label}"), subtitle)], [Paragraph(paragraph_text(f"Cấp bậc: {level_label}"), subtitle), Paragraph(paragraph_text(f"Mã báo cáo: {interview_id}"), subtitle)]], colWidths=[110 * mm, 68 * mm])
    header.setStyle(TableStyle([("SPAN", (0, 1), (1, 1)), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0B2447")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 8 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 8 * mm), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))
    story = [header, Spacer(1, 6 * mm), Paragraph("1. Tóm tắt điều hành", heading)]

    chart_width, chart_height = 110 * mm, 48 * mm
    competency_chart = Drawing(chart_width, chart_height)
    competency_chart.add(String(0, chart_height - 4 * mm, "HỒ SƠ NĂNG LỰC", fontName="DejaVu-Bold", fontSize=8, fillColor=colors.HexColor("#334155")))
    for index, (label, value) in enumerate(competency_profile[:4]):
        y = chart_height - (11 + index * 9) * mm
        competency_chart.add(String(0, y + 1.5 * mm, label, fontName="DejaVu", fontSize=7.5, fillColor=colors.HexColor("#475569")))
        competency_chart.add(Rect(35 * mm, y, 61 * mm, 3.5 * mm, fillColor=colors.HexColor("#E2E8F0"), strokeColor=None))
        competency_chart.add(Rect(35 * mm, y, max(0, min(value, 10)) * 6.1 * mm, 3.5 * mm, fillColor=colors.HexColor("#2563EB"), strokeColor=None))
        competency_chart.add(String(99 * mm, y + 0.4 * mm, score_label(value), fontName="DejaVu-Bold", fontSize=7.5, fillColor=colors.HexColor("#1E3A5F")))
    executive = Table([[Paragraph("<b>ĐIỂM ĐÁNH GIÁ AI</b><br/>" + score_label(average) + f"<br/><br/><b>Khuyến nghị</b><br/>{recommendation}<br/><br/><font size=8>Đây là dữ liệu hỗ trợ hội đồng tuyển dụng đưa ra quyết định.</font>", body), competency_chart]], colWidths=[62 * mm, 116 * mm])
    executive.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F8FAFC")), ("BACKGROUND", (1, 0), (1, 0), colors.white), ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm), ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm)]))
    interview_info = [[Paragraph("<b>Trạng thái</b>", small), Paragraph(paragraph_text(status_labels.get(report.get("status"), report.get("status") or "—")), body)], [Paragraph("<b>Câu trả lời ghi nhận</b>", small), Paragraph(str(len(report["answers"])), body)], [Paragraph("<b>Phương pháp tính</b>", small), Paragraph("Follow-up chỉ được cộng khi có điểm cao hơn câu gốc.", body)]]
    info_table = Table(interview_info, colWidths=[52 * mm, 126 * mm])
    info_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm)]))
    story.extend([executive, Spacer(1, 5 * mm), info_table, Paragraph("2. Nhận định trọng tâm", heading)])

    insights = [Paragraph(f"<b>Điểm mạnh</b><br/>{paragraph_text(report.get('overall_strengths') or 'Chưa có nhận định.')}", body), Paragraph(f"<b>Điểm cần làm rõ / cải thiện</b><br/>{paragraph_text(report.get('overall_weaknesses') or 'Chưa có nhận định.')}", body)]
    insight_table = Table([insights], colWidths=[89 * mm, 89 * mm])
    insight_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm)]))
    story.extend([insight_table, Paragraph("3. Bảng tổng hợp theo cụm câu hỏi", heading)])

    type_labels = competency_labels
    score_rows = [[Paragraph("<b>Câu</b>", small), Paragraph("<b>Năng lực đánh giá</b>", small), Paragraph("<b>Follow-up</b>", small), Paragraph("<b>Điểm nhóm</b>", small)]]
    for group in groups.values():
        root = next((answer for answer in group["answers"] if "." not in str(answer.get("question_number") or "")), None)
        question_type = (root or {}).get("question_type") or "General"
        score_rows.append([Paragraph(f"Câu {group['number']}", body), Paragraph(paragraph_text(type_labels.get(question_type, question_type)), body), Paragraph(str(sum("." in str(answer.get("question_number") or "") for answer in group["answers"])), body), Paragraph(f"<b>{score_label(group['score'])}</b>", body)])
    score_table = Table(score_rows, colWidths=[28 * mm, 82 * mm, 34 * mm, 34 * mm], repeatRows=1)
    score_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F7")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0EA")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 1), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm)]))
    story.extend([score_table, Paragraph("4. Phụ lục: chi tiết câu trả lời", heading), Paragraph("Phần này lưu lại bằng chứng cho việc xem xét của hội đồng tuyển dụng.", small)])
    for group in groups.values():
        attempt = f" · Lần phỏng vấn {group['attempt']}" if group["attempt"] > 1 else ""
        story.extend([Spacer(1, 5 * mm), Paragraph(f"CÂU {group['number']}{attempt}  ·  Điểm nhóm {score_label(group['score'])}", question)])
        for answer in group["answers"]:
            question_number = str(answer.get("question_number") or "")
            kind = f"Follow-up {question_number.split('.', 1)[1]}" if "." in question_number else "Câu hỏi gốc"
            answer_score = score_map.get(answer.get("ai_level"))
            answer_block = Table([[Paragraph(paragraph_text(f"{kind} · {score_label(answer_score)} · {answer.get('ai_level') or 'Chưa đánh giá'}"), small)], [Paragraph(paragraph_text(answer.get("question_text") or "Nội dung câu hỏi"), question)], [Paragraph(paragraph_text(answer.get("transcript") or "Không có bản ghi nội dung."), body)]], colWidths=[178 * mm])
            answer_block.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F1F5F9")), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm)]))
            story.extend([Spacer(1, 2.5 * mm), answer_block])
            if answer.get("ai_feedback"):
                story.append(Paragraph(paragraph_text(f"Nhận xét AI: {answer['ai_feedback']}"), small))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawCentredString(A4[0] / 2, 9 * mm, f"PAI Hire · Trang {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    safe_name = unicodedata.normalize("NFD", candidate_name)
    safe_name = "".join(char for char in safe_name if not unicodedata.combining(char))
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", safe_name).strip("-") or "ung-vien"
    return StreamingResponse(BytesIO(buffer.getvalue()), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="bao-cao-phong-van-{safe_name}.pdf"'})
