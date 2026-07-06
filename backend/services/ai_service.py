import json
import uuid
import httpx
import re
import edge_tts
from pathlib import Path
from openai import AsyncOpenAI
from backend.config import SCORE_PROMPT, EVAL_PROMPT, SOFT_SKILL_EVAL_PROMPT, HOD_QUESTIONS_PROMPT,  OPENAI_API_KEY, ELEVENLABS_API_KEY, OUTPUT_DIR, QUESTION_AUDIO_DIR, CV_UPLOAD_DIR, PASS_SCORE, _DEFAULT_EXPERIENCE, BASE_DIR, _find_position_files, _parse_q0306
from backend.database import db

async def _tts(text: str, out_path: Path) -> None:
    """Sinh audio TTS và lưu vào out_path. Bỏ qua nếu đã tồn tại."""
    if out_path.exists():
        return
    import edge_tts
    communicate = edge_tts.Communicate(text, voice="vi-VN-HoaiMyNeural")
    await communicate.save(str(out_path))


async def _do_score_cv(app_id: str, cv_path: Path, job_id: str, level: str = "Junior"):

    from backend.services.document_service import extract_cv_text, get_jd_content
    from backend.services.prep_service import _create_prep
    from backend.services.email_service import send_pass_email, send_fail_email

    cv_text = extract_cv_text(cv_path)
    jd_text = get_jd_content(job_id)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        prompt = SCORE_PROMPT.format(jd=jd_text[:4000], cv=cv_text[:5000])
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        # Tính lại tổng từ sub-scores — không tin AI tự tính
        g1 = result.get("group1", {})
        g2 = result.get("group2", {})
        we = g1.get("work_experience", {})
        ed = g1.get("education", {})
        sub = (
            float(we.get("years", 0))
            + float(we.get("relevance", 0))
            + float(we.get("achievements", 0))
            + float(ed.get("degree", 0))
            + float(ed.get("major", 0))
            + float(ed.get("certs", 0))
            + float(g1.get("technical_skills", 0))
            + float(g2.get("cv_quality", 0))
            + float(g2.get("projects", 0))
            + float(g2.get("leadership", 0))
        )
        # Làm tròn bội số 0.25
        total  = round(round(sub * 4) / 4, 2)
        result["total_score"] = total
        status = "passed" if total >= PASS_SCORE else "failed"

        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET cv_score=?, score_breakdown=?, ai_summary=?, status=? WHERE id=?",
                (total, json.dumps(result, ensure_ascii=False), result.get("summary", ""), status, app_id),
            )
            row = conn.execute(
                "SELECT name, email, job_id FROM cv_applications WHERE id=?", (app_id,)
            ).fetchone()

        print(f"[CV Score] {app_id} → {total}/10 ({status})")

        if row:
            if status == "passed":
                # Gen prep + TTS trước, sau đó mới gửi email
                # Ứng viên mở link là có audio sẵn ngay, không cần loading
                print(f"[CV Score] Đang gen prep cho {app_id}...")
                try:
                    await _create_prep(row["job_id"], app_id, level=level)
                    print(f"[CV Score] Prep xong, gửi email cho {row['email']}")
                except Exception as e:
                    print(f"[CV Score] Prep error (vẫn gửi email): {e}")
                send_pass_email(row["name"], row["email"], row["job_id"], app_id, level=level)
            else:
                send_fail_email(row["name"], row["email"], row["job_id"], app_id)

    except Exception as e:
        print(f"[CV Score Error] {app_id}: {e}")
        with db() as conn:
            conn.execute("UPDATE cv_applications SET status='error' WHERE id=?", (app_id,))


async def _do_evaluate_interview(interview_id: str, position_id: str, answer_rows: list):
    """STT từng câu → GPT-4o đánh giá.
    Nếu có nhiều answers cùng question_number (re-interview), dùng answer MỚI NHẤT.
    Technical/Experience: 4 mức có xếp bậc.
    Soft Skill: phân tích định tính, không xếp bậc (ai_level = NULL).
    """
    # Deduplicate: giữ answer mới nhất cho mỗi question_number
    deduped: dict[str, dict] = {}
    for r in answer_rows:
        qn = r["question_number"]
        if qn not in deduped or r.get("created_at", "") > deduped[qn].get("created_at", ""):
            deduped[qn] = r
    answer_rows = list(deduped.values())

    print(f"[Eval] Bắt đầu đánh giá {interview_id}")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        # Lấy câu hỏi kinh nghiệm cá nhân hoá từ prep
        prep_questions = {
            "07": _DEFAULT_EXPERIENCE["q07"],
            "08": _DEFAULT_EXPERIENCE["q08"],
        }
        with db() as conn:
            iv = conn.execute(
                "SELECT prep_id FROM interviews WHERE id=?", (interview_id,)
            ).fetchone()
            if iv and iv["prep_id"]:
                prep = conn.execute(
                    "SELECT q07_text, q08_text FROM interview_prep WHERE id=?",
                    (iv["prep_id"],)
                ).fetchone()
                if prep:
                    prep_questions["07"] = prep["q07_text"]
                    prep_questions["08"] = prep["q08_text"]

        type_count = {"Technical": 0, "Soft Skill": 0, "Experience": 0}

        for row in answer_rows:
            qn      = row["question_number"]
            q_type  = row["question_type"]
            audio_p = BASE_DIR / row["audio_path"]

            # ── 1. ElevenLabs STT ───────────────────────────────
            transcript = ""
            try:
                import httpx
                async with httpx.AsyncClient(timeout=60) as hx:
                    with open(audio_p, "rb") as f:
                        r = await hx.post(
                            "https://api.elevenlabs.io/v1/speech-to-text",
                            headers={"xi-api-key": ELEVENLABS_API_KEY},
                            files={"file": (audio_p.name, f, "audio/webm")},
                            data={"model_id": "scribe_v2", "language_code": "vi"},
                        )
                transcript = r.json().get("text", "").strip()
            except Exception as e:
                print(f"[Eval] STT lỗi câu {qn}: {e}")

            # ── 2. Xác định câu hỏi ────────────────────────────
            idx = type_count.get(q_type, 0)
            type_count[q_type] = idx + 1

            if qn in prep_questions:
                question = prep_questions[qn]
            elif qn in ("01", "02", "03", "04"):
                md_path, _ = _find_position_files(position_id)
                question   = _parse_q0306(md_path).get(qn, "") if md_path else ""
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
                        max_tok = 350
                    else:
                        # Xếp 4 mức
                        prompt = EVAL_PROMPT.format(
                            position=position_id.replace("_", " "),
                            q_type=q_type,
                            q_num=qn,
                            question=question,
                            transcript=transcript,
                        )
                        max_tok = 400

                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=max_tok,
                    )
                    raw = resp.choices[0].message.content.strip()
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                    ev  = json.loads(raw)

                    if q_type != "Soft Skill":
                        valid = {"nắm vững", "am hiểu", "có biết qua", "không biết"}
                        lv = ev.get("level", "")
                        ai_level = lv if lv in valid else "không biết"

                    ai_feedback  = ev.get("feedback", "")
                    strengths    = ev.get("strengths", "")
                    improvements = ev.get("improvements", "")
                    
                    normalized_transcript = ev.get("normalized_transcript", "")
                    if normalized_transcript and len(normalized_transcript) > 5:
                        transcript = normalized_transcript

                except Exception as e:
                    print(f"[Eval] GPT lỗi câu {qn}: {e}")
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
                    WHERE interview_id=? AND question_number=?
                """, (transcript, ai_level, ai_feedback, combined_notes.strip(),
                      question, interview_id, qn))

            print(f"[Eval] {interview_id} câu {qn} [{q_type}] → {ai_level or 'định tính'}")

        # ── §8 Output #8: HOD suggested questions ──────────────
        try:
            with db() as conn:
                iv_info = conn.execute(
                    "SELECT position_id, level FROM interviews WHERE id=?", (interview_id,)
                ).fetchone()
                ans_rows = conn.execute("""
                    SELECT question_number, question_type, transcript, ai_level, ai_feedback
                    FROM answers WHERE interview_id=? ORDER BY question_number
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
            hod_raw = re.sub(r"^```(?:json)?\s*", "", hod_raw)
            hod_raw = re.sub(r"\s*```$", "", hod_raw)
            hod_data = json.loads(hod_raw)
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
            overall_raw = re.sub(r"^```(?:json)?\s*", "", overall_raw)
            overall_raw = re.sub(r"\s*```$", "", overall_raw)
            overall_data = json.loads(overall_raw)

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
        print(f"[Eval] Hoàn thành {interview_id}")

    except Exception as e:
        print(f"[Eval] Lỗi tổng: {e}")


