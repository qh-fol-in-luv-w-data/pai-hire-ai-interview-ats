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
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTION_META, CATEGORY_LABELS, BASE_DIR, LEVEL_ORDER

from backend.services.prep_service import _create_prep, _prep_from_row
from backend.services.ai_service import _do_evaluate_interview
from backend.services.ai_service import _tts
from backend.config import OPENAI_API_KEY, ELEVENLABS_API_KEY
from backend.services.email_service import send_pass_email, send_fail_email, send_interview_reminder
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


@router.post("/interview/evaluate-step")
async def evaluate_step(
    audio: UploadFile = File(...),
    question_text: str = Form(...),
    question_type: str = Form(...),
    history: str = Form("[]"),
):
    # 1. Save temp audio
    req_id = uuid.uuid4().hex[:8]
    in_audio_path = TEMP_PUSHBACKS_DIR / f"{req_id}_in.webm"
    in_audio_path.write_bytes(await audio.read())

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

    # 3. Parse History
    import json
    try:
        hist_data = json.loads(history)
    except:
        hist_data = []

    history_text = ""
    for h in hist_data:
        role = "HR" if h.get("role") == "assistant" else "Ứng viên"
        history_text += f"{role}: {h.get('content')}\n"

    # 4. LLM GPT-4o cho Chuẩn hoá và Phản biện
    prompt = f"""Bạn là một chuyên gia phỏng vấn nhân sự.
Loại câu hỏi: {question_type}
Câu hỏi ban đầu: "{question_text}"

Dưới đây là lịch sử trao đổi:
{history_text}
Câu trả lời mới nhất của ứng viên (STT thô): "{transcript}"

NHIỆM VỤ CỦA BẠN:
1. Chuẩn hoá đoạn STT thô của câu trả lời mới nhất (sửa lỗi chính tả, bỏ từ thừa như "à", "ừm", giữ nguyên toàn bộ ý chính và phong cách nói của ứng viên).
2. Đánh giá xem câu trả lời đã giải quyết triệt để vấn đề chưa.
   - NẾU "Loại câu hỏi" KHÔNG PHẢI LÀ "Experience", hoặc câu trả lời đã đủ chi tiết, hoặc ứng viên chốt không còn ý nào bổ sung, hoặc ứng viên trả lời quá lan man: Trả về chữ "PASS" cho phần phản biện.
   - NẾU "Loại câu hỏi" LÀ "Experience" và vẫn còn mập mờ cần đào sâu thêm: Đặt ra ĐÚNG 1 câu hỏi phản biện ngắn gọn, trực diện (dưới 30 từ).

BẮT BUỘC trả về định dạng JSON hợp lệ (không kèm theo block code markdown), gồm 2 field:
{{
  "normalized_transcript": "<đoạn STT đã chuẩn hoá>",
  "pushback_question": "<câu hỏi phản biện hoặc 'PASS'>"
}}
"""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300
        )
        ai_resp_raw = resp.choices[0].message.content.strip()
        import re
        ai_resp_raw = re.sub(r"^```(?:json)?\s*", "", ai_resp_raw)
        ai_resp_raw = re.sub(r"\s*```$", "", ai_resp_raw)
        
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

    if ai_resp.upper() == "PASS" or "PASS" in ai_resp.upper():
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
        "pushback_audio": f"/temp_pushbacks/{out_audio_name}",
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
        cv_ext      = Path(cv_file.filename).suffix or ".pdf"
        cv_filename = f"cv{cv_ext}"
        cv_path     = session_dir / cv_filename
        cv_path.write_bytes(await cv_file.read())
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

            q_type = QUESTION_META.get(qn, "General")

            audio_name = f"{key}.webm"
            audio_path = session_dir / audio_name
            audio_path.write_bytes(await upload.read())
            
            answer_rows.append({
                "interview_id":    interview_id,
                "question_number": question_number,
                "question_type":   q_type,
                "audio_path":      str(audio_path.relative_to(BASE_DIR)),
                "created_at":      now,
            })

    # ── Re-interview: lưu thêm vào interview GỐC, không tạo mới ──
    if reiv:
        with db() as conn:
            orig = conn.execute(
                "SELECT id, candidate_id, position_id FROM interviews WHERE id=?", (reiv,)
            ).fetchone()
            if not orig:
                raise HTTPException(404, f"Không tìm thấy interview gốc: {reiv}")

            # Chèn answers mới vào interview gốc (giữ nguyên answers cũ để HR so sánh)
            reiv_rows = [{**r, "interview_id": reiv} for r in answer_rows]
            conn.executemany("""
                INSERT INTO answers
                    (interview_id, question_number, question_type, audio_path, created_at)
                VALUES (:interview_id, :question_number, :question_type, :audio_path, :created_at)
            """, reiv_rows)

            # Cập nhật interview gốc
            conn.execute(
                "UPDATE interviews SET status='submitted', submitted_at=?, prep_id=COALESCE(?, prep_id) WHERE id=?",
                (now, prep_id or None, reiv),
            )

        print(f"[✓] Re-interview {reiv} | {len(answer_rows)} answers added")
        background.add_task(_do_evaluate_interview, reiv, position_id, reiv_rows)
        return {"ok": True, "interview_id": reiv, "reinterview": True, "answers_saved": len(answer_rows)}

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
                (id, candidate_id, position_id, cv_filename, cv_path, prep_id, level, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interview_id, candidate_id, position_id,
            cv_filename, str(cv_path.relative_to(BASE_DIR)), prep_id, level, now,
        ))

        conn.executemany("""
            INSERT INTO answers
                (interview_id, question_number, question_type, audio_path, created_at)
            VALUES (:interview_id, :question_number, :question_type, :audio_path, :created_at)
        """, answer_rows)

    print(f"[✓] {interview_id} | candidate={candidate_id} | position={position_id}")
    background.add_task(_do_evaluate_interview, interview_id, position_id, answer_rows)

    return {
        "ok":            True,
        "interview_id":  interview_id,
        "candidate_id":  candidate_id,
        "answers_saved": len(answer_rows),
    }


@router.get("/interview/{interview_id}")
def get_interview(interview_id: str):
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
            "SELECT * FROM answers WHERE interview_id = ? ORDER BY question_number",
            (interview_id,)
        ).fetchall()

    return {
        **dict(row),
        "answers": [dict(a) for a in answers],
    }


@router.get("/candidate/{candidate_id}/interviews")
def get_candidate_interviews(candidate_id: str):
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
def list_interviews(status: str = None, position_id: str = None, limit: int = 50):
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
            "SELECT interview_id, question_number, question_type, audio_path, created_at FROM answers WHERE interview_id=? ORDER BY created_at",
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
            "SELECT * FROM answers WHERE interview_id=? ORDER BY question_number",
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


