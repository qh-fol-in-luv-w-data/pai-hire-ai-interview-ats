import json
import uuid
import httpx
import re
import edge_tts
from pathlib import Path
from openai import AsyncOpenAI
from backend.config import SCORE_PROMPT, EVAL_PROMPT, SOFT_SKILL_EVAL_PROMPT, HOD_QUESTIONS_PROMPT,  OPENAI_API_KEY, ELEVENLABS_API_KEY, OUTPUT_DIR, QUESTION_AUDIO_DIR, CV_UPLOAD_DIR, PASS_SCORE, _DEFAULT_EXPERIENCE, BASE_DIR, _find_position_files, _parse_q0306
from backend.database import db, log_application_event
from backend.security import media_content_type_for_path


def _extract_json_object(raw: str) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


SCORE_WEIGHTS = {
    "c1_technical_skills": 0.20,
    "c2_experience": 0.20,
    "c3_education": 0.10,
    "c4_industry": 0.10,
    "c5_career_path": 0.10,
    "c6_achievements": 0.10,
    "c7_soft_skills": 0.05,
    "c8_language_cv": 0.05,
    "c9_stability": 0.05,
    "c10_ai_overall": 0.05,
}


def normalize_cv_score(score_result: dict) -> tuple[dict, float]:
    """Clamp 1-5 rubric scores and calculate the weighted 1-5 total."""
    c = score_result.setdefault("criteria_scores", {})
    normalized = {}
    for key in SCORE_WEIGHTS:
        try:
            value = int(round(float(c.get(key, 1) or 1)))
        except Exception:
            value = 1
        normalized[key] = min(max(value, 1), 5)
    score_result["criteria_scores"] = normalized

    raw_weighted_total = score_result.get("weighted_total")
    try:
        score_result["ai_weighted_total"] = round(float(raw_weighted_total), 2)
    except Exception:
        pass

    weighted_total = sum(score * SCORE_WEIGHTS[key] for key, score in normalized.items())
    total = round(min(max(weighted_total, 1.0), 5.0), 2)

    evidence = score_result.setdefault("evidence", {})
    for key in ("matched_requirements", "missing_requirements", "transferable_strengths", "quantified_achievements"):
        if not isinstance(evidence.get(key), list):
            evidence[key] = []
    if not isinstance(score_result.get("risk_flags"), list):
        score_result["risk_flags"] = []
    if not isinstance(score_result.get("interview_focus"), list):
        score_result["interview_focus"] = []
    confidence = score_result.setdefault("confidence", {})
    if confidence.get("level") not in {"low", "medium", "high"}:
        confidence["level"] = "medium"
    confidence.setdefault("reason", "CV/JD có đủ thông tin cơ bản để đánh giá sơ bộ.")

    score_result["score_scale"] = "1-5_weighted"
    score_result["criteria_weights"] = SCORE_WEIGHTS
    score_result["weighted_total"] = total
    score_result["total_score"] = total
    return score_result, total


async def _tts(text: str, out_path: Path, force: bool = False) -> None:
    """Sinh audio atomically; corrupt/empty cached files are regenerated."""
    if not force and out_path.exists() and out_path.stat().st_size > 512:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)
    import edge_tts
    communicate = edge_tts.Communicate(text, voice="vi-VN-HoaiMyNeural")
    await communicate.save(str(tmp_path))
    if not tmp_path.exists() or tmp_path.stat().st_size <= 512:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("TTS không tạo được audio hợp lệ")
    tmp_path.replace(out_path)


async def _do_score_cv(app_id: str, cv_path: Path, job_id: str, level: str = "Junior"):

    from backend.services.document_service import extract_cv_text, get_jd_content, get_all_jobs
    from backend.services.prep_service import _create_prep
    from backend.services.email_service import send_pass_email, send_fail_email

    cv_text = extract_cv_text(cv_path)
    jd_text = get_jd_content(job_id)
    job_row = next((j for j in get_all_jobs(include_inactive=True) if j["id"] == job_id), None)
    job_title = job_row["title"] if job_row else job_id.replace("_", " ")

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        # Get pass score from settings
        pass_score = PASS_SCORE
        with db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='cv_pass_score'").fetchone()
            if row and row["value"]:
                try:
                    pass_score = float(row["value"])
                    if pass_score > 5:
                        pass_score = pass_score / 2
                except:
                    pass

        prompt = SCORE_PROMPT.format(jd=jd_text[:4000], cv=cv_text[:5000], pass_score=pass_score)
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2200,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        result, total = normalize_cv_score(result)
        ai_verdict = "passed" if total >= pass_score else "failed"
        pending_status = f"waiting_for_reply_{ai_verdict}"

        # Generate deep analysis questions
        try:
            deep_result = await generate_deep_questions(cv_text, jd_text, job_id=job_id, position=job_title, level=level)
            deep_qs = deep_result.get("questions", [])
            deep_coverage = deep_result.get("coverage", "medium")
            result["deep_questions"] = deep_qs
            result["deep_questions_coverage"] = deep_coverage
        except Exception as e:
            print(f"[CV Score] Deep questions error: {e}")
            result["deep_questions"] = []
            result["deep_questions_coverage"] = None
            deep_qs = []
            deep_coverage = None

        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET cv_score=?, score_breakdown=?, ai_summary=?, status=? WHERE id=?",
                (total, json.dumps(result, ensure_ascii=False), result.get("summary", ""), pending_status, app_id),
            )
            row = conn.execute(
                "SELECT name, email, job_id FROM cv_applications WHERE id=?", (app_id,)
            ).fetchone()

        print(f"[CV Score] {app_id} → {total}/5 (AI gợi ý: {ai_verdict}) — Chờ ứng viên trả lời")
        if row:
            log_application_event(
                app_id,
                row["email"],
                "cv_scored",
                f"AI đã đánh giá hồ sơ: {round(total, 2)}/5, đề xuất {ai_verdict}.",
                {"score": total, "verdict": ai_verdict, "status": pending_status},
            )

        if row and deep_qs and deep_coverage != "low":
            from backend.services.email_service import send_deep_questions_email
            send_deep_questions_email(row["name"], row["email"], row["job_id"], app_id, deep_qs)
            log_application_event(
                app_id,
                row["email"],
                "deep_questions_sent",
                f"Chúng tôi đã gửi email chứa {len(deep_qs)} câu hỏi bổ sung tới hộp thư của bạn — vui lòng kiểm tra email và trả lời để tiếp tục quy trình.",
                {"question_count": len(deep_qs), "coverage": deep_coverage},
            )
        elif row and deep_qs and deep_coverage == "low":
            log_application_event(
                app_id,
                row["email"],
                "deep_questions_skipped_low_coverage",
                f"Bỏ qua gửi {len(deep_qs)} câu hỏi bổ sung vì CV không cùng lĩnh vực với JD (coverage=low).",
                {"question_count": len(deep_qs), "coverage": deep_coverage},
            )

    except Exception as e:
        print(f"[CV Score Error] {app_id}: {e}")
        with db() as conn:
            conn.execute("UPDATE cv_applications SET status='error' WHERE id=?", (app_id,))
            row = conn.execute("SELECT email FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        if row:
            log_application_event(app_id, row["email"], "cv_score_error", "AI đánh giá hồ sơ bị lỗi.", {"error": str(e)})


async def _do_evaluate_interview(interview_id: str, position_id: str, answer_rows: list):
    """STT từng câu → GPT-4o đánh giá.
    Nếu có nhiều answers cùng question_number (re-interview), dùng answer MỚI NHẤT.
    Technical/Experience: 4 mức có xếp bậc.
    Soft Skill: phân tích định tính, không xếp bậc (ai_level = NULL).
    """
    # Deduplicate: giữ answer mới nhất cho mỗi question_number
    deduped: dict[str, dict] = {}
    for r in answer_rows:
        qn = f"{r.get('attempt_number', 1)}:{r['question_number']}"
        if qn not in deduped or r.get("created_at", "") > deduped[qn].get("created_at", ""):
            deduped[qn] = r
    answer_rows = list(deduped.values())

    print(f"[Eval] Bắt đầu đánh giá {interview_id}")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        # Lấy toàn bộ câu hỏi từ prep_service
        prep_data = {}
        with db() as conn:
            iv = conn.execute(
                "SELECT prep_id FROM interviews WHERE id=?", (interview_id,)
            ).fetchone()
            if iv and iv["prep_id"]:
                prep_row = conn.execute(
                    "SELECT * FROM interview_prep WHERE id=?",
                    (iv["prep_id"],)
                ).fetchone()
                if prep_row:
                    from backend.services.prep_service import _prep_from_row
                    prep_data = _prep_from_row(prep_row)

        type_count = {"Technical": 0, "Soft Skill": 0, "Experience": 0}

        for row in answer_rows:
            qn      = row["question_number"]
            q_type  = row["question_type"]
            audio_p = BASE_DIR / row["audio_path"]
            attempt_number = int(row.get("attempt_number", 1) or 1)

            # ── 1. Transcript/STT ───────────────────────────────
            # Frontend đã gọi /evaluate-step và có thể gửi transcript chuẩn hơn.
            # Chỉ STT lại khi chưa có transcript để tránh lần STT thứ hai trả rỗng/lệch.
            transcript = (row.get("transcript") or "").strip()
            if not transcript:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=60) as hx:
                        with open(audio_p, "rb") as f:
                            r = await hx.post(
                                "https://api.elevenlabs.io/v1/speech-to-text",
                                headers={"xi-api-key": ELEVENLABS_API_KEY},
                                files={"file": (audio_p.name, f, media_content_type_for_path(audio_p))},
                                data={"model_id": "scribe_v2", "language_code": "vi"},
                            )
                    transcript = r.json().get("text", "").strip()
                except Exception as e:
                    print(f"[Eval] STT lỗi câu {qn}: {e}")

            # ── 2. Xác định câu hỏi ────────────────────────────
            idx = type_count.get(q_type, 0)
            type_count[q_type] = idx + 1

            if row.get("question_text"):
                question = row["question_text"]
            elif prep_data and qn in prep_data.get("questions", {}):
                question = prep_data["questions"][qn]["text"]
            elif "." in str(qn) and prep_data and str(qn).split(".", 1)[0] in prep_data.get("questions", {}):
                question = prep_data["questions"][str(qn).split(".", 1)[0]]["text"]
            else:
                question = ""


            # ── 3. GPT-4o đánh giá ─────────────────────────────
            ai_level     = None          # None = soft skill (không xếp mức)
            ai_feedback  = ""
            strengths    = ""
            improvements = ""

            if transcript:
                try:
                    if q_type == "Soft Skill":
                        # Phân tích định tính
                        prompt = SOFT_SKILL_EVAL_PROMPT.format(
                            question=question,
                            transcript=transcript,
                        )
                        max_tok = 8000
                    else:
                        # Xếp 4 mức
                        prompt = EVAL_PROMPT.format(
                            position=position_id.replace("_", " "),
                            q_type=q_type,
                            q_num=qn,
                            question=question,
                            transcript=transcript,
                        )
                        max_tok = 8000

                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=max_tok,
                        response_format={"type": "json_object"},
                    )
                    raw = resp.choices[0].message.content.strip()
                    ev  = _extract_json_object(raw)

                    if q_type != "Soft Skill":
                        valid = {"nắm vững", "am hiểu", "có biết qua", "không biết"}
                        lv = ev.get("level", "")
                        ai_level = lv if lv in valid else "không biết"

                    ai_feedback  = ev.get("feedback", "")
                    strengths    = ev.get("strengths", "")
                    improvements = ev.get("improvements", "")
                    if not ai_feedback:
                        ai_feedback = (
                            "AI đã xử lý transcript nhưng không trả về nhận xét chi tiết. "
                            "Vui lòng xem transcript/audio để HR xác nhận thêm."
                        )
                    
                    normalized_transcript = ev.get("normalized_transcript", "")
                    if normalized_transcript and len(normalized_transcript) > 5:
                        transcript = normalized_transcript

                except Exception as e:
                    print(f"[Eval] GPT lỗi câu {qn}: {e}")
                    ai_level = None
                    ai_feedback = (
                        "Hệ thống chưa phân tích được câu trả lời này do lỗi xử lý AI. "
                        "Transcript đã được lưu, HR cần nghe lại audio hoặc bấm đánh giá lại."
                    )
                    improvements = "Cần đánh giá lại thủ công hoặc chạy lại AI."
            else:
                ai_feedback = "Không có transcript đủ rõ để AI chấm điểm câu trả lời này."
                if q_type != "Soft Skill":
                    ai_level = "không biết"

            # ── 4. Lưu DB ──────────────────────────────────────
            combined_notes = ""
            if strengths:    combined_notes += f"✓ {strengths}\n"
            if improvements: combined_notes += f"△ {improvements}"

            with db() as conn:
                conn.execute("""
                    UPDATE answers
                    SET transcript=?, ai_level=?, ai_feedback=?, notes=?, question_text=?
                    WHERE interview_id=? AND question_number=? AND attempt_number=?
                """, (transcript, ai_level, ai_feedback, combined_notes.strip(),
                      question, interview_id, qn, attempt_number))

            print(f"[Eval] {interview_id} câu {qn} [{q_type}] → {ai_level or 'định tính'}")

        # ── §8 Output #8: HOD suggested questions ──────────────
        try:
            with db() as conn:
                iv_info = conn.execute(
                    "SELECT position_id, level FROM interviews WHERE id=?", (interview_id,)
                ).fetchone()
                ans_rows = conn.execute("""
                    SELECT question_number, question_type, transcript, ai_level, ai_feedback
                    FROM answers WHERE interview_id=? ORDER BY attempt_number, question_number
                """, (interview_id,)).fetchall()

            summary_lines = []
            for a in ans_rows:
                lvl = f"[{a['ai_level']}]" if a["ai_level"] else "[định tính]"
                summary_lines.append(
                    f"Q{a['question_number']} ({a['question_type']}) {lvl}: {(a['ai_feedback'] or '')[:200]}"
                )
            summary = "\n".join(summary_lines)

            hod_prompt = HOD_QUESTIONS_PROMPT.format(
                position=iv_info["position_id"].replace("_", " ") if iv_info else position_id,
                level=(iv_info["level"] or "Junior") if iv_info else "Junior",
                summary=summary,
            )
            hod_resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": hod_prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            hod_raw = hod_resp.choices[0].message.content.strip()
            hod_data = _extract_json_object(hod_raw)
            hod_questions = json.dumps(hod_data.get("questions", []), ensure_ascii=False)

            with db() as conn:
                conn.execute(
                    "UPDATE interviews SET hod_questions=? WHERE id=?",
                    (hod_questions, interview_id)
                )
            print(f"[Eval] HOD questions saved for {interview_id}")
        except Exception as e:
            print(f"[Eval] HOD questions error: {e}")

        # Overall eval
        try:
            overall_prompt = f"""\
Dựa trên lịch sử trả lời của ứng viên vị trí {position_id}:
{summary}

Hãy đóng vai trò là một chuyên gia nhân sự. Viết 3 phần nhận xét tổng quan CHI TIẾT, RÕ RÀNG VÀ CHUYÊN SÂU về ứng viên này (viết bằng tiếng Việt). Lời văn phải giống như một báo cáo đánh giá chuyên nghiệp do con người viết, không dùng văn phong máy móc.
1. Điểm mạnh (Strengths)
2. Điểm yếu cần cải thiện (Weaknesses)
3. Năng lực nổi trội (Outstanding Competencies)

Trả về CHỈ JSON theo định dạng (mỗi phần viết thành 1 đoạn văn hoặc gạch đầu dòng chi tiết):
{{
  "strengths": "...",
  "weaknesses": "...",
  "competencies": "..."
}}
"""
            overall_resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": overall_prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            overall_raw = overall_resp.choices[0].message.content.strip()
            overall_data = _extract_json_object(overall_raw)

            with db() as conn:
                conn.execute(
                    "UPDATE interviews SET overall_strengths=?, overall_weaknesses=?, overall_competencies=? WHERE id=?",
                    (overall_data.get("strengths", ""), overall_data.get("weaknesses", ""), overall_data.get("competencies", ""), interview_id)
                )
            print(f"[Eval] Overall eval saved for {interview_id}")
        except Exception as e:
            print(f"[Eval] Lỗi generate overall eval: {e}")

        with db() as conn:
            conn.execute(
                "UPDATE interviews SET status='evaluated' WHERE id=?", (interview_id,)
            )
            iv_row = conn.execute(
                """
                SELECT c.email, p.app_ref
                FROM interviews i
                LEFT JOIN candidates c ON c.id=i.candidate_id
                LEFT JOIN interview_prep p ON p.id=i.prep_id
                WHERE i.id=?
                """,
                (interview_id,),
            ).fetchone()
        if iv_row and iv_row["email"]:
            log_application_event(
                iv_row["app_ref"],
                iv_row["email"],
                "interview_evaluated",
                f"AI đã xử lý và đánh giá xong bài phỏng vấn {interview_id}.",
                {"interview_id": interview_id},
            )
        print(f"[Eval] Hoàn thành {interview_id}")

    except Exception as e:
        print(f"[Eval] Lỗi tổng: {e}")



async def analyze_candidate_reply(cv_text: str, jd_text: str, deep_questions: list, candidate_reply: str) -> dict:
    """Sử dụng GPT-4o để đánh giá câu trả lời của ứng viên."""
    from openai import AsyncOpenAI
    from backend.config import OPENAI_API_KEY, EVALUATE_REPLY_PROMPT
    import json
    
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY chưa được cấu hình.")
        
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Format deep questions into readable text
    dq_text = "\n".join([f"Câu {i+1}: {q.get('question_text', '') if isinstance(q, dict) else str(q)}" for i, q in enumerate(deep_questions)])
    
    prompt = EVALUATE_REPLY_PROMPT.format(
        cv_text=cv_text[:5000], 
        jd_text=jd_text[:4000],
        deep_questions=dq_text,
        candidate_reply=candidate_reply
    )
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "return_reply_evaluation",
                "description": "Trả về kết quả đánh giá câu trả lời của ứng viên.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "evaluation": {"type": "string", "description": "Đánh giá chi tiết câu trả lời."},
                        "red_flags": {"type": "array", "items": {"type": "string"}, "description": "Các điểm đáng ngờ hoặc chưa thỏa đáng."},
                        "strengths": {"type": "array", "items": {"type": "string"}, "description": "Các điểm mạnh thể hiện qua câu trả lời."},
                        "recommendation": {"type": "string", "enum": ["Phê duyệt", "Từ chối"], "description": "Đề xuất cuối cùng."},
                        "score_adjustment": {"type": "number", "description": "Mức điểm cộng/trừ (từ -1.0 đến 1.0) cho CV gốc."},
                        "score_adjustment_reason": {"type": "string", "description": "Lý do cụ thể vì sao cộng/trừ/giữ nguyên điểm sau khi đọc câu trả lời."}
                    },
                    "required": ["evaluation", "red_flags", "strengths", "recommendation", "score_adjustment", "score_adjustment_reason"]
                }
            }
        }
    ]
    
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "return_reply_evaluation"}}
    )
    
    tool_call = resp.choices[0].message.tool_calls[0]
    result_json = tool_call.function.arguments
    return json.loads(result_json)

async def generate_deep_questions(
    cv_text: str, jd_text: str, job_id: str | None = None,
    position: str = "", level: str = "", num_questions: int = 5,
) -> dict:
    """Sinh câu hỏi bổ sung sau khi chấm CV. Dùng chung khung năng lực JD
    (backend.services.competency_service) với luồng tạo bộ đề phỏng vấn: mỗi câu
    hỏi được ràng buộc vào một năng lực cốt lõi cụ thể của JD (PROBE nếu CV có
    bằng chứng, TRANSFER nếu không) thay vì lọc hậu kiểm theo từ khoá."""
    from backend.config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY chưa được cấu hình.")

    from backend.services.competency_service import generate_competency_questions
    result = await generate_competency_questions(cv_text, jd_text, job_id, position, level, num_questions)
    questions = [q["question"] for q in result["questions"]]
    return {"coverage": result["coverage"], "questions": questions}

async def evaluate_cv_round_1(cv_text: str, jd_text: str, criteria_text: str) -> dict:
    """Đánh giá vòng 1: Kiểm tra xem CV có đủ thông tin không. Nếu thiếu trả về câu hỏi bổ sung."""
    from openai import AsyncOpenAI
    from backend.config import OPENAI_API_KEY, CV_EVAL_ROUND_1_PROMPT
    
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY chưa được cấu hình.")
        
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = CV_EVAL_ROUND_1_PROMPT.format(
        cv_text=cv_text[:5000], 
        jd_text=jd_text[:4000],
        criteria_text=criteria_text[:2000]
    )
    
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1000,
        response_format={ "type": "json_object" }
    )
    
    import json
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw)

async def evaluate_cv_round_2(cv_text: str, jd_text: str, criteria_text: str, answers_text: str) -> dict:
    """Đánh giá vòng 2: Chấm điểm dựa trên CV + câu trả lời bổ sung. Trả về kết quả cuối cùng."""
    from openai import AsyncOpenAI
    from backend.config import OPENAI_API_KEY, CV_EVAL_ROUND_2_PROMPT
    
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY chưa được cấu hình.")
        
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = CV_EVAL_ROUND_2_PROMPT.format(
        cv_text=cv_text[:5000], 
        jd_text=jd_text[:4000],
        criteria_text=criteria_text[:2000],
        answers_text=answers_text[:3000]
    )
    
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1000,
        response_format={ "type": "json_object" }
    )
    
    import json
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw)
