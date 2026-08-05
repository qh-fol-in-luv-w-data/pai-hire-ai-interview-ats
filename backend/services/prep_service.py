import time
import uuid
import re
import json
from backend.database import db
from backend.services.document_service import extract_cv_text, get_all_jobs, get_jd_content, resolve_job_id
from backend.config import QUESTION_AUDIO_DIR, OPENAI_API_KEY, BASE_DIR, INTRO_TEMPLATE, _GEN_AUDIO_NAMES, QUESTIONS_BANK, _DEFAULT_EXPERIENCE
from backend.services.ai_service import _tts
from backend.config import CV_QUESTIONS_PROMPT, _parse_q0306, _find_position_files

DEFAULT_PART_1_LIMIT = 11
DEFAULT_PART_2_LIMIT = 7
DEFAULT_FOLLOW_UP_LIMIT = 5
MAX_PART_1_LIMIT = 11
MAX_PART_2_LIMIT = 13
MAX_FOLLOW_UP_LIMIT = 5


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def normalize_interview_config(config: dict | None) -> dict:
    config = config or {}
    normalized = {
        "PART_1_DEFAULT": _bounded_int(
            config.get("PART_1_DEFAULT"),
            DEFAULT_PART_1_LIMIT,
            1,
            MAX_PART_1_LIMIT,
        ),
        "PART_2_GENERATED": _bounded_int(
            config.get("PART_2_GENERATED"),
            DEFAULT_PART_2_LIMIT,
            0,
            MAX_PART_2_LIMIT,
        ),
        "PART_3_FOLLOW_UP": _bounded_int(
            config.get("PART_3_FOLLOW_UP"),
            DEFAULT_FOLLOW_UP_LIMIT,
            0,
            MAX_FOLLOW_UP_LIMIT,
        ),
    }
    if "IS_UNLIMITED" in config:
        normalized["IS_UNLIMITED"] = bool(config.get("IS_UNLIMITED"))
    if config.get("VALID_FROM"):
        normalized["VALID_FROM"] = str(config.get("VALID_FROM"))
    if config.get("VALID_UNTIL"):
        normalized["VALID_UNTIL"] = str(config.get("VALID_UNTIL"))
    return normalized


def _infer_generated_question_type(text: str) -> str:
    lowered = (text or "").lower()
    soft_terms = (
        "giao tiếp", "phối hợp", "mâu thuẫn", "bất đồng", "áp lực",
        "deadline", "stakeholder", "đội nhóm", "thuyết phục", "phản hồi",
    )
    technical_terms = (
        "công cụ", "hệ thống", "phần mềm", "ats", "linkedin", "job board",
        "star", "boolean", "kpi", "metric", "dashboard", "báo cáo",
        "phương pháp", "quy trình chuẩn",
    )
    experience_terms = (
        "trong cv", "kinh nghiệm", "từng làm", "đã thực hiện", "dẫn dắt",
        "vai trò", "kết quả", "thành tích", "dự án", "nhiệm vụ", "bối cảnh",
        "tại ", "quy trình", "case",
    )
    if any(term in lowered for term in soft_terms):
        return "Soft Skill"
    if any(term in lowered for term in experience_terms):
        return "Experience"
    if any(term in lowered for term in technical_terms):
        return "Technical"
    return "Experience"


def _question_type_for_prep(n: str, text: str, is_generated: bool = False) -> str:
    if is_generated:
        return _infer_generated_question_type(text)
    lowered = (text or "").lower()
    if n == "01" or "giới thiệu" in lowered:
        return "General"
    return QUESTIONS_BANK.get(n, {}).get("type", "General")


def _allow_follow_up_for_prep(n: str, text: str, is_generated: bool = False) -> bool:
    return _question_type_for_prep(n, text, is_generated) in {"Technical", "Experience"}


_TECH_QUESTION_TERMS = (
    "api", "backend", "frontend", "framework", "database", "sql", "python",
    "javascript", "typescript", "react", "node", "docker", "kubernetes",
    "cloud", "aws", "server", "system design", "microservice", "deploy",
    "code", "coding", "lập trình", "phần mềm", "cơ sở dữ liệu", "thuật toán",
)
_TECH_JD_TERMS = (
    "developer", "engineer", "frontend", "backend", "fullstack", "devops",
    "data", "ai/ml", "automation tester", "qa/qc", "system admin",
    "công nghệ thông tin", "lập trình", "phần mềm", "dữ liệu",
)
_JD_ANCHORS = (
    "jd yêu cầu", "vị trí này", "yêu cầu công việc", "trách nhiệm chính",
    "mô tả công việc", "công việc này", "vai trò này", "yêu cầu trong jd",
    "một trách nhiệm chính", "ở vị trí này", "công việc sẽ cần",
    "vai trò này cần", "liên quan đến", "theo yêu cầu", "phần tuyển dụng",
    "phần sàng lọc", "phần phỏng vấn", "phần biên soạn",
)
_CV_ANCHORS = (
    "trong cv", "cv của bạn", "cv bạn", "bạn có đề cập", "kinh nghiệm tại",
    "vai trò tại", "dự án", "thành tích", "nhiệm vụ",
)
_GENERIC_QUESTION_TERMS = (
    "giới thiệu", "mục tiêu nghề nghiệp", "điểm mạnh", "điểm yếu",
    "khó khăn gì", "cải thiện quy trình", "quản lý thời gian", "làm việc đa nhiệm",
    "mâu thuẫn nào", "dự án hoặc nhiệm vụ", "chia sẻ một ví dụ cụ thể",
)
_JD_REQUIREMENT_TERMS = (
    "yêu cầu", "trách nhiệm", "nhiệm vụ", "kinh nghiệm", "kỹ năng",
    "thành thạo", "phụ trách", "quản lý", "thực hiện", "triển khai",
    "xây dựng", "theo dõi", "kiểm soát", "phân tích", "báo cáo",
    "phối hợp", "đảm bảo", "tối ưu", "vận hành", "quy trình",
    "tuyển dụng", "nhân sự", "bảo hiểm", "tiền lương", "đào tạo",
)


def _jd_requirement_lines(jd_text: str, limit: int = 12) -> list[str]:
    lines = []
    seen = set()
    for raw in (jd_text or "").splitlines():
        line = raw.strip(" -*•\t\r\n")
        line = re.sub(r"\s+", " ", line)
        if len(line) < 24 or len(line) > 240:
            continue
        lowered = line.lower()
        if lowered in seen:
            continue
        if any(term in lowered for term in _JD_REQUIREMENT_TERMS):
            lines.append(line)
            seen.add(lowered)
        if len(lines) >= limit:
            break
    if lines:
        return lines
    chunks = re.split(r"(?<=[.!?。])\s+|\n+", jd_text or "")
    for raw in chunks:
        line = raw.strip(" -*•\t\r\n")
        line = re.sub(r"\s+", " ", line)
        if 24 <= len(line) <= 240 and line.lower() not in seen:
            lines.append(line)
            seen.add(line.lower())
        if len(lines) >= limit:
            break
    return lines


def _question_relevant_to_jd(question: str, jd_text: str) -> bool:
    text = (question or "").lower()
    jd = (jd_text or "").lower()
    if not text.strip():
        return False
    jd_is_tech = any(term in jd for term in _TECH_JD_TERMS)
    asks_old_tech = any(term in text for term in _TECH_QUESTION_TERMS)
    if asks_old_tech and not jd_is_tech:
        return False
    has_jd_anchor = any(anchor in text for anchor in _JD_ANCHORS)
    has_cv_anchor = any(anchor in text for anchor in _CV_ANCHORS)
    if not has_jd_anchor and not has_cv_anchor:
        return False
    if has_cv_anchor and not any(term in text for term in ("jd", "vị trí", "yêu cầu", "công việc", "trách nhiệm")):
        return False
    too_generic = any(term in text for term in _GENERIC_QUESTION_TERMS)
    if too_generic and not has_jd_anchor and not has_cv_anchor:
        return False
    return True


def _jd_gap_question(position: str, jd_text: str, offset: int = 0) -> str:
    jd_hint = "yêu cầu quan trọng nhất trong JD"
    jd_lines = _jd_requirement_lines(jd_text)
    if jd_lines:
        jd_hint = jd_lines[offset % len(jd_lines)][:180]
    return (
        f"Ở vị trí {position}, phần {jd_hint} là một nội dung cần kiểm chứng kỹ. "
        "Anh/chị đã từng làm phần nào tương tự trong các kinh nghiệm ở CV chưa; nếu có, hãy chia sẻ vai trò trực tiếp, cách làm và kết quả đo được, "
        "còn nếu chưa thì anh/chị sẽ chuẩn bị thêm như thế nào để bắt nhịp nhanh?"
    )


def _dedupe_questions(questions: list[str]) -> list[str]:
    kept = []
    signatures = set()
    for question in questions:
        cleaned = re.sub(r"\s+", " ", (question or "").strip())
        cleaned = re.sub(r"\bgap\b", "điểm cần bổ sung", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("bù đắp gap", "bổ sung phần còn thiếu")
        cleaned = cleaned.replace("kế hoạch bù đắp", "cách anh/chị chuẩn bị thêm")
        if not cleaned:
            continue
        words = re.findall(r"[\wÀ-ỹ]+", cleaned.lower())
        signature = " ".join(words[:18])
        if signature in signatures:
            continue
        signatures.add(signature)
        kept.append(cleaned)
    return kept


async def _create_prep(position_id: str, app_ref: str,
                       level: str = "Junior") -> dict:
    """
    Gen câu hỏi kinh nghiệm từ CV + TTS toàn bộ.
    Trả về dict {prep_id, intro_audio, questions}.
    """
    now     = time.strftime("%Y-%m-%dT%H:%M:%S")
    prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()

    limits = normalize_interview_config(None)
    limit_p1 = limits["PART_1_DEFAULT"]
    limit_p2 = limits["PART_2_GENERATED"]
    limit_p3 = limits["PART_3_FOLLOW_UP"]
    if app_ref:
        with db() as conn:
            row = conn.execute("SELECT interview_config FROM cv_applications WHERE id=?", (app_ref,)).fetchone()
            if row and row["interview_config"]:
                try:
                    cfg = normalize_interview_config(json.loads(row["interview_config"]))
                    limit_p1 = cfg["PART_1_DEFAULT"]
                    limit_p2 = cfg["PART_2_GENERATED"]
                    limit_p3 = cfg["PART_3_FOLLOW_UP"]
                except:
                    pass

    app_job_id = ""
    if app_ref:
        with db() as conn:
            app_row = conn.execute(
                "SELECT job_id FROM cv_applications WHERE id=?", (app_ref,)
            ).fetchone()
        if app_row and app_row["job_id"]:
            app_job_id = app_row["job_id"]

    canonical_job_id, resolved_level = resolve_job_id(app_job_id or position_id)
    jd_lookup_id = canonical_job_id or app_job_id or position_id
    jobs      = get_all_jobs()
    job       = next((j for j in jobs if j["id"] == jd_lookup_id), None)
    job_title = job["title"] if job else position_id.replace("_", " ")
    jd_text   = get_jd_content(jd_lookup_id)
    if not jd_text and canonical_job_id and canonical_job_id != position_id:
        jd_text = get_jd_content(position_id)

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
                        level=level or resolved_level,
                        jd_text=jd_text[:5000],
                        cv_text=cv_text[:4000],
                        num_gen=num_gen,
                        json_format=json_format
                    )
                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=max(1000, num_gen * 180),
                        response_format={"type": "json_object"},
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

                    ai_texts = _dedupe_questions([
                        text for text in ai_texts
                        if _question_relevant_to_jd(text, jd_text)
                    ])
                    while len(ai_texts) < num_gen:
                        ai_texts.append(_jd_gap_question(job_title, jd_text, len(ai_texts)))

                    for i, text in enumerate(ai_texts[:num_gen]):
                        generated_qs[str(i + start_idx).zfill(2)] = text

                except Exception as e:
                    print(f"[Prep] CV questions error: {e}")

    if not generated_qs and limit_p2 > 0:
        start_idx = len(q_texts) + 1
        fallback_texts = [
            _DEFAULT_EXPERIENCE["q07"],
            _DEFAULT_EXPERIENCE["q08"],
        ]
        while len(fallback_texts) < limit_p2:
            fallback_texts.append(_jd_gap_question(job_title, jd_text, len(fallback_texts)))
        for i, text in enumerate(fallback_texts[:limit_p2]):
            generated_qs[str(start_idx + i).zfill(2)] = text

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
                try:
                    await _tts(INTRO_TEMPLATE.format(title=job_title), dst_intro)
                except Exception as e:
                    print(f"[Prep] Intro TTS error: {e}")

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
                try:
                    await _tts(text, dst)
                except Exception as e:
                    print(f"[Prep] Q{k} TTS error: {e}")
        
        print(f"[Prep] Hoàn tất chuẩn bị audio cho {prep_id}")
    except Exception as e:
        print(f"[Prep] TTS error: {e}")

    questions = {
        n: {
            "text":      q_texts[n],
            "audio_url": f"/audio/{audio_map[n]}",
            "type":      _question_type_for_prep(n, q_texts[n], n in generated_qs),
            "is_generated": n in generated_qs,
            "allow_follow_up": _allow_follow_up_for_prep(n, q_texts[n], n in generated_qs),
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
    
    limits = normalize_interview_config(None)
    limit_p1 = limits["PART_1_DEFAULT"]
    limit_p2 = limits["PART_2_GENERATED"]
    limit_p3 = limits["PART_3_FOLLOW_UP"]
    if app_ref:
        with db() as conn:
            cfg_row = conn.execute("SELECT interview_config FROM cv_applications WHERE id=?", (app_ref,)).fetchone()
            if cfg_row and cfg_row["interview_config"]:
                try:
                    cfg = normalize_interview_config(json.loads(cfg_row["interview_config"]))
                    limit_p1 = cfg["PART_1_DEFAULT"]
                    limit_p2 = cfg["PART_2_GENERATED"]
                    limit_p3 = cfg["PART_3_FOLLOW_UP"]
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

    if len(generated_qs) > limit_p2:
        generated_qs = dict(
            sorted(generated_qs.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999)[:limit_p2]
        )
        
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
                "type":      _question_type_for_prep(n, q_texts[n], n in generated_qs),
                "is_generated": n in generated_qs,
                "allow_follow_up": _allow_follow_up_for_prep(n, q_texts[n], n in generated_qs),
            }
            for n in q_texts if q_texts[n]
        },
        "follow_up_limit": limit_p3
    }
