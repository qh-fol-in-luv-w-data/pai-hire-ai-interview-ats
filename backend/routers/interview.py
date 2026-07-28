import os
import uuid
import time
import json
import httpx
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, BackgroundTasks, File, Form, UploadFile, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from backend.database import db
from backend.services.ai_service import _tts
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS, BASE_DIR, LEVEL_ORDER

from backend.services.prep_service import _create_prep, _prep_from_row
from backend.services.ai_service import _do_evaluate_interview
from backend.services.ai_service import _tts
from backend.config import OPENAI_API_KEY, ELEVENLABS_API_KEY
from backend.services.email_service import send_pass_email, send_fail_email, send_interview_reminder
from backend.security import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_CV_EXTENSIONS,
    MAX_AUDIO_UPLOAD_BYTES,
    MAX_CV_UPLOAD_BYTES,
    read_upload_limited,
    signed_temp_file_url,
)
router = APIRouter()

@router.post("/interview/prep")
async def create_interview_prep(
    position_id: str = Form(...),
    app_ref:     str = Form(None),
    level:       str = Form("Junior"),
):
    # Nếu app_ref đã có prep sẵn → trả luôn, không gen lại
    if app_ref:
        with db() as conn:
            existing = conn.execute(
                "SELECT * FROM interview_prep WHERE app_ref=? ORDER BY created_at DESC LIMIT 1",
                (app_ref,)
            ).fetchone()
        if existing:
            print(f"[Prep] Dùng prep sẵn {existing['id']} cho {app_ref}")
            return _prep_from_row(existing)

    return await _create_prep(position_id, app_ref, level=level)


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
    follow_up_limit: int = Form(5),
):
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

    # 2. STT via ElevenLabs
    transcript = ""
    try:
        import httpx
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
        print(f"[Eval] STT error: {e}")

    if not transcript:
        return {"need_pushback": False, "transcript": transcript}

    question_number = (question_number or "").split("_", 1)[0]
    if follow_up_limit <= 0 or question_number == "01" or "giới thiệu" in (question_text or "").lower():
        return {"need_pushback": False, "transcript": transcript}

    # Theo yêu cầu: Chỉ follow-up các câu hỏi chuyên môn (Technical) và nghề nghiệp (Experience)
    if question_type not in ["Technical", "Experience"]:
        return {"need_pushback": False, "transcript": transcript}

    # 3. Parse History
    import json
    try:
        hist_data = json.loads(history)
    except:
        hist_data = []
        
    # Tính số lượng câu hỏi follow-up đã hỏi
    # Số lần AI đã hỏi (trừ câu gốc đầu tiên ra)
    follow_up_count = sum(1 for h in hist_data if h.get("role") == "assistant") - 1
    if follow_up_count >= follow_up_limit:
        return {"need_pushback": False, "transcript": transcript}

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

2. Đánh giá câu trả lời và Quyết định follow-up:
   - `follow_up_limit` chỉ là GIỚI HẠN TỐI ĐA, KHÔNG phải số câu bắt buộc phải hỏi đủ.
   - Mặc định ưu tiên trả về "PASS" nếu câu trả lời đã trả lời đúng trọng tâm, có đủ ý chính để đánh giá, hoặc không còn điểm nghi vấn đáng đào sâu.
   - Chỉ đặt follow-up khi có THIẾU SÓT/RỦI RO RÕ RÀNG ảnh hưởng đến đánh giá, ví dụ: thiếu ví dụ thực tế cho năng lực cốt lõi, thiếu số liệu/kết quả trong thành tích quan trọng, mâu thuẫn với CV/JD, trả lời né tránh, hoặc nói "không biết/chưa có kinh nghiệm" ở yêu cầu trọng yếu.
   - Không hỏi follow-up chỉ vì câu trả lời chưa thật dài, chưa hoàn hảo về diễn đạt, hoặc đã đủ hiểu để chấm điểm.
   - Nếu đã từng hỏi follow-up mà ứng viên trả lời thêm đủ để đánh giá, trả về "PASS"; không cố hỏi tiếp.

3. Nếu thật sự cần hỏi follow-up, câu hỏi phải:
   - Ngắn gọn (dưới 25 từ), trực tiếp, không có câu mở đầu xã giao.
   - Yêu cầu ứng viên CHO VÍ DỤ CỤ THỂ, CON SỐ, hoặc TÌNH HUỐNG thực tế.
   - Bắt đầu bằng: "Cụ thể hơn...", "Bạn có thể kể ví dụ...", "Kết quả cụ thể là gì?", "Bạn đã làm gì khi...?" v.v.

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

    # 5. TTS for pushback
    out_audio_name = f"{req_id}_out.mp3"
    out_audio_path = TEMP_PUSHBACKS_DIR / out_audio_name
    try:
        await _tts(ai_resp, out_audio_path)
    except Exception as e:
        print(f"[EvalStep] TTS lỗi: {e}")
        return {"need_pushback": False, "transcript": transcript}

    return {
        "need_pushback": True,
        "pushback_text": ai_resp,
        "pushback_audio": signed_temp_file_url(out_audio_name),
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
    prep_id      = form.get("prep_id")
    level        = form.get("level", "Junior")
    reiv         = form.get("reiv")
    cv_file      = form.get("cv_file")
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

            q_meta = question_meta.get(qn, {}) if isinstance(question_meta, dict) else {}
            original_qn = str(q_meta.get("original_n") or qn).split("_", 1)[0]
            q_type = q_meta.get("type") or QUESTIONS_BANK.get(original_qn, {}).get("type", "General")

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

            answer_rows.append({
                "interview_id":    interview_id,
                "question_number": question_number,
                "question_type":   q_type,
                "question_text":   q_text,
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
                    (interview_id, question_number, question_type, question_text, audio_path, created_at, time_spent, attempt_number)
                VALUES (:interview_id, :question_number, :question_type, :question_text, :audio_path, :created_at, :time_spent, :attempt_number)
            """, [{**r, "time_spent": time_spent.get(r["question_number"].split(".")[0], 0)} for r in reiv_rows])


            # Cập nhật interview gốc
            conn.execute(
                "UPDATE interviews SET status='submitted', submitted_at=?, prep_id=COALESCE(?, prep_id) WHERE id=?",
                (now, prep_id or None, reiv),
            )

        print(f"[✓] Re-interview {reiv} | attempt={next_attempt} | {len(answer_rows)} answers added")
        background.add_task(_do_evaluate_interview, reiv, position_id, reiv_rows)
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
                (id, candidate_id, position_id, cv_filename, cv_path, prep_id, level, submitted_at, tab_switches, status, reinterview_scope)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interview_id, candidate_id, position_id,
            cv_filename, str(cv_path.relative_to(BASE_DIR)), prep_id, level, now, tab_switches, "submitted", '[]'
        ))


        conn.executemany("""
            INSERT INTO answers
                (interview_id, question_number, question_type, question_text, audio_path, created_at, time_spent, attempt_number)
            VALUES (:interview_id, :question_number, :question_type, :question_text, :audio_path, :created_at, :time_spent, :attempt_number)
        """, [{**r, "time_spent": time_spent.get(r["question_number"].split(".")[0], 0)} for r in answer_rows])

    print(f"[✓] {interview_id} | candidate={candidate_id} | position={position_id}")
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
            SELECT i.*, c.name as candidate_name
            FROM interviews i
            LEFT JOIN candidates c ON i.candidate_id = c.id
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
                   ROUND(AVG(CASE a.ai_level
                     WHEN 'nắm vững'    THEN 10.0
                     WHEN 'am hiểu'     THEN 7.5
                     WHEN 'có biết qua' THEN 5.0
                     WHEN 'không biết'  THEN 0.0
                     ELSE NULL END), 1) as avg_score
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
            "SELECT interview_id, question_number, question_type, audio_path, created_at, attempt_number FROM answers WHERE interview_id=? ORDER BY attempt_number, created_at",
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

    # Avg score: chỉ tính Technical + Experience (Soft Skill không xếp mức)
    scored_levels = [
        r["ai_level"] for r in rows
        if r["ai_level"] and r["ai_level"] in LEVEL_ORDER
    ]
    scores    = [LEVEL_ORDER[l] for l in scored_levels]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    summary   = {l: scored_levels.count(l) for l in LEVEL_ORDER}

    groups = {}
    for r in rows:
        qt = r["question_type"] or "Unknown"
        groups.setdefault(qt, []).append(r)

    return {
        "interview_id":   interview_id,
        "candidate_name": iv["candidate_name"],
        "position":       iv["position_id"],
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
