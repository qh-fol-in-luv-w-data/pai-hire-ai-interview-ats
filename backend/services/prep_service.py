import time
import uuid
import re
import json
from backend.database import db
from backend.services.document_service import extract_cv_text, get_all_jobs
from backend.config import CV_QUESTIONS_PROMPT, QUESTION_AUDIO_DIR, OPENAI_API_KEY, BASE_DIR, INTRO_TEMPLATE, _GEN_AUDIO_NAMES, QUESTIONS_BANK, _DEFAULT_EXPERIENCE
from backend.services.ai_service import _tts
from backend.config import CV_QUESTIONS_PROMPT,  _parse_q0306, _find_position_files

async def _create_prep(position_id: str, app_ref: str,
                       level: str = "Junior") -> dict:
    """
    Gen câu hỏi kinh nghiệm từ CV + TTS toàn bộ.
    Trả về dict {prep_id, intro_audio, questions}.
    """
    now     = time.strftime("%Y-%m-%dT%H:%M:%S")
    prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()

    jobs      = get_all_jobs()
    job       = next((j for j in jobs if j["id"] == position_id), None)
    job_title = job["title"] if job else position_id.replace("_", " ")

    md_path, gen_audio_dir = _find_position_files(position_id)
    q_texts = _parse_q0306(md_path) if md_path else {}
    if not q_texts:
        q_texts = {
            "01": "Bạn hãy giới thiệu về bản thân và kinh nghiệm làm việc liên quan đến vị trí này.",
            "02": "Mục tiêu nghề nghiệp của bạn trong 3-5 năm tới là gì?",
            "03": "Hãy chia sẻ về một dự án hoặc nhiệm vụ khó khăn nhất mà bạn từng thực hiện.",
            "04": "Bạn tiếp cận việc học hỏi kiến thức mới như thế nào trong công việc?",
            "05": "Hãy kể về một lần bạn có quan điểm trái ngược với đồng nghiệp và cách giải quyết.",
            "06": "Bạn làm gì khi nhận được quá nhiều công việc cùng lúc với deadline sát nhau?",
        }

    q07_text = q_texts.get("07", _DEFAULT_EXPERIENCE["q07"])
    q08_text = q_texts.get("08", _DEFAULT_EXPERIENCE["q08"])

    if app_ref and OPENAI_API_KEY:
        with db() as conn:
            row = conn.execute(
                "SELECT cv_path FROM cv_applications WHERE id=?", (app_ref,)
            ).fetchone()
        if row and row["cv_path"]:
            cv_text = extract_cv_text(BASE_DIR / row["cv_path"])
            if cv_text.strip():
                try:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
                    prompt = CV_QUESTIONS_PROMPT.format(
                        position=job_title,
                        level=level,
                        cv_text=cv_text[:4000],
                    )
                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=300,
                    )
                    raw = resp.choices[0].message.content.strip()
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                    parsed = json.loads(raw)
                    q07_text = parsed.get("q05", q07_text)
                    q08_text = parsed.get("q06", q08_text)
                except Exception as e:
                    print(f"[Prep] CV questions error: {e}")

    q_texts["07"] = q07_text
    q_texts["08"] = q08_text

    with db() as conn:
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, q07_text, q08_text, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (prep_id, app_ref, position_id, "", "", q07_text, q08_text, now),
        )

    audio_map = {
        "01": f"{position_id}_q01.mp3",
        "02": f"{position_id}_q02.mp3",
        "03": f"{position_id}_q03.mp3",
        "04": f"{position_id}_q04.mp3",
        "05": f"{position_id}_q05.mp3",
        "06": f"{position_id}_q06.mp3",
        "07": f"{prep_id}_q07.mp3",
        "08": f"{prep_id}_q08.mp3",
    }
    intro_file = f"intro_{position_id}.mp3"

    try:
        import shutil
        
        # Intro: copy từ outputs/question_audio (nếu có), hoặc fallback về gen TTS
        dst_intro = QUESTION_AUDIO_DIR / intro_file
        if not dst_intro.exists():
            src_intro = BASE_DIR / "outputs" / "question_audio" / intro_file
            if src_intro.exists():
                shutil.copy2(src_intro, dst_intro)
            else:
                await _tts(INTRO_TEMPLATE.format(title=job_title), dst_intro)

        # Q01-Q06: copy từ Generated_Audio (đã có sẵn)
        if gen_audio_dir and gen_audio_dir.is_dir():
            for n, src_name in _GEN_AUDIO_NAMES.items():
                dst = QUESTION_AUDIO_DIR / audio_map[n]
                if not dst.exists():
                    src = gen_audio_dir / src_name
                    if src.exists():
                        shutil.copy2(src, dst)
                    else:
                        print(f"[Prep] Thiếu audio gốc: {src}")

        # Q07/Q08: gen edge-tts mới theo CV ứng viên
        await _tts(q_texts["07"], QUESTION_AUDIO_DIR / f"{prep_id}_q07.mp3")
        await _tts(q_texts["08"], QUESTION_AUDIO_DIR / f"{prep_id}_q08.mp3")
        
        print(f"[Prep] Hoàn tất chuẩn bị audio cho {prep_id}")
    except Exception as e:
        print(f"[Prep] TTS error: {e}")

    questions = {
        n: {
            "text":      q_texts[n],
            "audio_url": f"/audio/{audio_map[n]}",
            "type":      QUESTIONS_BANK.get(n, {}).get("type", "General"),
        }
        for n in q_texts
    }
    return {
        "prep_id":     prep_id,
        "intro_audio": f"/audio/{intro_file}",
        "questions":   questions,
    }


def _prep_from_row(row) -> dict:
    """Rebuild response dict từ DB row (prep đã tồn tại)."""
    pid     = row["id"]
    pos     = row["position_id"]
    md_path, _ = _find_position_files(pos)
    q0106   = _parse_q0306(md_path) if md_path else {}
    q_texts = {
        "01": q0106.get("01", ""), "02": q0106.get("02", ""),
        "03": q0106.get("03", ""), "04": q0106.get("04", ""),
        "05": q0106.get("05", ""), "06": q0106.get("06", ""),
        "07": row["q07_text"] if "q07_text" in row.keys() else "",
        "08": row["q08_text"] if "q08_text" in row.keys() else "",
    }
    audio_map = {
        "01": f"{pos}_q01.mp3",
        "02": f"{pos}_q02.mp3",
        "03": f"{pos}_q03.mp3",
        "04": f"{pos}_q04.mp3",
        "05": f"{pos}_q05.mp3",
        "06": f"{pos}_q06.mp3",
        "07": f"{pid}_q07.mp3",
        "08": f"{pid}_q08.mp3",
    }
    return {
        "prep_id":     pid,
        "intro_audio": f"/audio/intro_{pos}.mp3",
        "questions": {
            n: {
                "text":      q_texts[n],
                "audio_url": f"/audio/{audio_map[n]}",
                "type":      QUESTIONS_BANK.get(n, {}).get("type", "General"),
            }
            for n in q_texts if q_texts[n]
        },
    }


