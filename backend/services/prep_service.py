import time
import uuid
import re
import json
from backend.database import db
from backend.services.document_service import extract_cv_text, get_all_jobs
from backend.config import CV_QUESTIONS_PROMPT, QUESTION_AUDIO_DIR, OPENAI_API_KEY, BASE_DIR, INTRO_TEMPLATE, _GEN_AUDIO_NAMES, QUESTIONS_BANK, _DEFAULT_EXPERIENCE
from backend.services.ai_service import _tts
from backend.config import CV_QUESTIONS_PROMPT,  _parse_q0306, _find_position_files


def _question_type_for_prep(n: str, text: str) -> str:
    lowered = (text or "").lower()
    if n == "01" or "giới thiệu" in lowered:
        return "General"
    return QUESTIONS_BANK.get(n, {}).get("type", "General")


def _allow_follow_up_for_prep(n: str, text: str) -> bool:
    return _question_type_for_prep(n, text) in {"Technical", "Experience"}


async def _create_prep(position_id: str, app_ref: str,
                       level: str = "Junior") -> dict:
    """
    Gen câu hỏi kinh nghiệm từ CV + TTS toàn bộ.
    Trả về dict {prep_id, intro_audio, questions}.
    """
    now     = time.strftime("%Y-%m-%dT%H:%M:%S")
    prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()

    limit_p1 = 11
    limit_p2 = 7
    limit_p3 = 5
    if app_ref:
        with db() as conn:
            row = conn.execute("SELECT interview_config FROM cv_applications WHERE id=?", (app_ref,)).fetchone()
            if row and row["interview_config"]:
                try:
                    cfg = json.loads(row["interview_config"])
                    limit_p1 = int(cfg.get("PART_1_DEFAULT", limit_p1))
                    limit_p2 = int(cfg.get("PART_2_GENERATED", limit_p2))
                    limit_p3 = int(cfg.get("PART_3_FOLLOW_UP", limit_p3))
                except:
                    pass

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
        
    if len(q_texts) > limit_p1:
        q_texts = dict(list(q_texts.items())[:limit_p1])
    elif len(q_texts) < limit_p1:
        # Bổ sung thêm câu hỏi từ QUESTIONS_BANK cho đủ limit_p1
        for k, v in QUESTIONS_BANK.items():
            if len(q_texts) >= limit_p1:
                break
            if not v.get("is_dynamic") and v["text"] not in q_texts.values():
                new_k = str(len(q_texts) + 1).zfill(2)
                q_texts[new_k] = v["text"]

    generated_qs = {}
    if app_ref and OPENAI_API_KEY and limit_p2 > 0:
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
                    
                    num_gen = limit_p2
                    start_idx = len(q_texts) + 1
                    json_format = ", ".join([f'"q{str(i+start_idx).zfill(2)}": "câu hỏi thứ {i+1}"' for i in range(num_gen)])
                    json_format = f"{{{json_format}}}"
                    
                    prompt = CV_QUESTIONS_PROMPT.format(
                        position=job_title,
                        level=level,
                        cv_text=cv_text[:4000],
                        num_gen=num_gen,
                        json_format=json_format
                    )
                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=600,
                    )
                    raw = resp.choices[0].message.content.strip()
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                    parsed = json.loads(raw)
                    
                    # Robust parsing: take all string values from parsed dict/list
                    ai_texts = []
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if isinstance(v, str): ai_texts.append(v)
                            elif isinstance(v, dict) and "text" in v: ai_texts.append(v["text"])
                    elif isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, str): ai_texts.append(item)
                            elif isinstance(item, dict) and "text" in item: ai_texts.append(item["text"])
                            
                    for i, text in enumerate(ai_texts[:num_gen]):
                        generated_qs[str(i + start_idx).zfill(2)] = text

                except Exception as e:
                    print(f"[Prep] CV questions error: {e}")

    if not generated_qs and limit_p2 > 0:
        start_idx = len(q_texts) + 1
        if limit_p2 >= 1: generated_qs[str(start_idx).zfill(2)] = _DEFAULT_EXPERIENCE["q07"]
        if limit_p2 >= 2: generated_qs[str(start_idx + 1).zfill(2)] = _DEFAULT_EXPERIENCE["q08"]

    for k, v in generated_qs.items():
        q_texts[k] = v

    generated_json = json.dumps(generated_qs, ensure_ascii=False)

    with db() as conn:
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, q07_text, q08_text, created_at, generated_questions)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (prep_id, app_ref, position_id, "", "", generated_qs.get("07", ""), generated_qs.get("08", ""), now, generated_json),
        )

    audio_map = {}
    for k in q_texts:
        if k not in generated_qs:
            audio_map[k] = f"{position_id}_q{k}.mp3"
        else:
            audio_map[k] = f"{prep_id}_q{k}.mp3"
            
    intro_file = f"intro_{position_id}.mp3"

    try:
        import shutil
        
        dst_intro = QUESTION_AUDIO_DIR / intro_file
        if not dst_intro.exists():
            src_intro = BASE_DIR / "outputs" / "question_audio" / intro_file
            if src_intro.exists():
                shutil.copy2(src_intro, dst_intro)
            else:
                await _tts(INTRO_TEMPLATE.format(title=job_title), dst_intro)

        if gen_audio_dir and gen_audio_dir.is_dir():
            for n, src_name in _GEN_AUDIO_NAMES.items():
                if n in audio_map:
                    dst = QUESTION_AUDIO_DIR / audio_map[n]
                    if not dst.exists():
                        src = gen_audio_dir / src_name
                        if src.exists():
                            shutil.copy2(src, dst)
                        else:
                            print(f"[Prep] Thiếu audio gốc: {src}")

        # Ensure all questions have TTS audio
        for k, text in q_texts.items():
            dst = QUESTION_AUDIO_DIR / audio_map[k]
            if not dst.exists():
                await _tts(text, dst)
        
        print(f"[Prep] Hoàn tất chuẩn bị audio cho {prep_id}")
    except Exception as e:
        print(f"[Prep] TTS error: {e}")

    questions = {
        n: {
            "text":      q_texts[n],
            "audio_url": f"/audio/{audio_map[n]}",
            "type":      _question_type_for_prep(n, q_texts[n]),
            "allow_follow_up": _allow_follow_up_for_prep(n, q_texts[n]),
        }
        for n in q_texts
    }
    return {
        "prep_id":         prep_id,
        "intro_audio":     f"/audio/{intro_file}",
        "questions":       questions,
        "follow_up_limit": limit_p3
    }


def _prep_from_row(row) -> dict:
    """Rebuild response dict từ DB row (prep đã tồn tại)."""
    pid     = row["id"]
    pos     = row["position_id"]
    app_ref = row["app_ref"]
    
    limit_p1 = 11
    limit_p3 = 5
    if app_ref:
        with db() as conn:
            cfg_row = conn.execute("SELECT interview_config FROM cv_applications WHERE id=?", (app_ref,)).fetchone()
            if cfg_row and cfg_row["interview_config"]:
                try:
                    cfg = json.loads(cfg_row["interview_config"])
                    limit_p1 = int(cfg.get("PART_1_DEFAULT", limit_p1))
                    limit_p3 = int(cfg.get("PART_3_FOLLOW_UP", limit_p3))
                except:
                    pass

    md_path, _ = _find_position_files(pos)
    q0106   = _parse_q0306(md_path) if md_path else {}
    if not q0106:
        q0106 = {
            "01": "Bạn hãy giới thiệu về bản thân và kinh nghiệm làm việc liên quan đến vị trí này.",
            "02": "Mục tiêu nghề nghiệp của bạn trong 3-5 năm tới là gì?",
            "03": "Hãy chia sẻ về một dự án hoặc nhiệm vụ khó khăn nhất mà bạn từng thực hiện.",
            "04": "Bạn tiếp cận việc học hỏi kiến thức mới như thế nào trong công việc?",
            "05": "Hãy kể về một lần bạn có quan điểm trái ngược với đồng nghiệp và cách giải quyết.",
            "06": "Bạn làm gì khi nhận được quá nhiều công việc cùng lúc với deadline sát nhau?",
        }
    
    if len(q0106) > limit_p1:
        q0106 = dict(list(q0106.items())[:limit_p1])
    elif len(q0106) < limit_p1:
        for k, v in QUESTIONS_BANK.items():
            if len(q0106) >= limit_p1:
                break
            if not v.get("is_dynamic") and v["text"] not in q0106.values():
                new_k = str(len(q0106) + 1).zfill(2)
                q0106[new_k] = v["text"]
        
    q_texts = {}
    for k, v in q0106.items():
        q_texts[k] = v
        
    generated_qs = {}
    if "generated_questions" in row.keys() and row["generated_questions"]:
        try:
            generated_qs = json.loads(row["generated_questions"])
        except:
            pass
    
    row_dict = dict(row)
    if not generated_qs:
        if row_dict.get("q07_text"): generated_qs["07"] = row_dict["q07_text"]
        if row_dict.get("q08_text"): generated_qs["08"] = row_dict["q08_text"]
        
    for k, v in generated_qs.items():
        q_texts[k] = v
        
    audio_map = {}
    for k in q_texts:
        if k not in generated_qs:
            audio_map[k] = f"{pos}_q{k}.mp3"
        else:
            audio_map[k] = f"{pid}_q{k}.mp3"

    return {
        "prep_id":     pid,
        "intro_audio": f"/audio/intro_{pos}.mp3",
        "questions": {
            n: {
                "text":      q_texts[n],
                "audio_url": f"/audio/{audio_map[n]}",
                "type":      _question_type_for_prep(n, q_texts[n]),
                "allow_follow_up": _allow_follow_up_for_prep(n, q_texts[n]),
            }
            for n in q_texts if q_texts[n]
        },
        "follow_up_limit": limit_p3
    }

