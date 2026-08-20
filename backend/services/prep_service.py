import hashlib
import time
import uuid
import re
import json
from backend.database import db
from backend.services.document_service import extract_cv_text, get_all_jobs, get_jd_content, resolve_job_id
from backend.config import QUESTION_AUDIO_DIR, OPENAI_API_KEY, BASE_DIR, INTRO_TEMPLATE, _GEN_AUDIO_NAMES, QUESTIONS_BANK, _DEFAULT_EXPERIENCE
from backend.services.ai_service import _tts
from backend.config import _parse_q0306, _find_position_files
from backend.services.competency_service import generate_competency_questions

DEFAULT_PART_1_LIMIT = 11
DEFAULT_PART_2_LIMIT = 7
DEFAULT_FOLLOW_UP_LIMIT = 5
MAX_PART_1_LIMIT = 11
MAX_PART_2_LIMIT = 13
MAX_FOLLOW_UP_LIMIT = 5

_FOLLOW_UP_ELIGIBLE_TYPES = {"Technical", "Experience"}

_FALLBACK_PART1_QUESTIONS = {
    "01": "Bạn hãy giới thiệu về bản thân và kinh nghiệm làm việc liên quan đến vị trí này.",
    "02": "Mục tiêu nghề nghiệp của bạn trong 3-5 năm tới là gì?",
    "03": "Hãy chia sẻ về một dự án hoặc nhiệm vụ khó khăn nhất mà bạn từng thực hiện.",
    "04": "Bạn tiếp cận việc học hỏi kiến thức mới như thế nào trong công việc?",
    "05": "Hãy kể về một lần bạn có quan điểm trái ngược với đồng nghiệp và cách giải quyết.",
    "06": "Bạn làm gì khi nhận được quá nhiều công việc cùng lúc với deadline sát nhau?",
}


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


def follow_up_total_limit(per_question_limit: int) -> int:
    """Trần TỔNG số câu đào sâu trong cả buổi phỏng vấn, tách khỏi trần MỖI câu
    hỏi (PART_3_FOLLOW_UP). Trước đây không có trần tổng — trần chỉ tính theo
    từng câu hỏi nên với bộ đề nhiều câu, tổng có thể lên tới per_question_limit
    × số câu được phép đào sâu. Nhân hệ số cố định thay vì thêm một trường cấu
    hình HR mới; điều chỉnh hệ số ở đây nếu cần khác biệt theo vị trí."""
    return max(0, min(per_question_limit * 3, 15))


def _audio_filename(text: str) -> str:
    """Tên file audio theo hash nội dung câu hỏi. Text đổi thì tên đổi — cache
    không còn thể phục vụ nhầm audio cũ cho nội dung mới, và vẫn dùng chung được
    giữa các ứng viên/prep có cùng nội dung câu hỏi."""
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:20]
    return f"q_{digest}.mp3"


def _infer_generated_question_type(text: str) -> str:
    """Đoán loại câu hỏi bằng từ khoá — chỉ dùng khi KHÔNG có type do model tự
    khai báo (đường dự phòng lúc AI sinh câu hỏi thất bại hoàn toàn, hoặc khi
    đọc lại prep cũ tạo trước khi có questions_json)."""
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


def _jd_gap_question(position: str, jd_text: str, offset: int = 0) -> str:
    """Câu hỏi dự phòng khi sinh câu hỏi theo năng lực JD thất bại hoàn toàn
    (không có CV, chưa cấu hình OPENAI_API_KEY, hoặc lỗi mạng) — KHÔNG dùng để
    lọc chất lượng, chỉ dùng để không để trống Phần 2."""
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
                       level: str = "Junior", prep_id: str | None = None) -> dict:
    """
    Gen câu hỏi kinh nghiệm từ CV + TTS toàn bộ, rồi ĐÓNG BĂNG kết quả vào cột
    questions_json. Một khi đã tạo, bộ đề của ứng viên này không đổi theo các
    lần đọc sau — sửa QUESTIONS_BANK, sửa file .md nguồn, hay đổi cấu hình
    PART_1_DEFAULT/PART_2_GENERATED sau khi tạo prep sẽ không còn làm trôi đề
    so với audio đã sinh cho ứng viên đó.

    prep_id: truyền vào khi caller đã tạo sẵn dòng placeholder (xem
    _run_prep_generation) — ghi đè đúng dòng đó thay vì tạo id mới.
    """
    now     = time.strftime("%Y-%m-%dT%H:%M:%S")
    prep_id = prep_id or ("PREP-" + uuid.uuid4().hex[:10].upper())

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
                except Exception:
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
        q_texts = dict(_FALLBACK_PART1_QUESTIONS)

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

    # Phần 2: câu hỏi ràng buộc theo năng lực cốt lõi của JD (PROBE nếu CV có
    # bằng chứng, TRANSFER nếu không) — độ phủ JD được bảo đảm bằng cấu trúc,
    # không phải bằng bộ lọc hậu kiểm theo từ khoá.
    generated_meta: dict[str, dict] = {}
    if app_ref and OPENAI_API_KEY and limit_p2 > 0:
        with db() as conn:
            row = conn.execute(
                "SELECT cv_path FROM cv_applications WHERE id=?", (app_ref,)
            ).fetchone()
        cv_text = ""
        if row and row["cv_path"]:
            cv_text = extract_cv_text(BASE_DIR / row["cv_path"])
        if cv_text.strip():
            try:
                start_idx = len(q_texts) + 1
                result = await generate_competency_questions(
                    cv_text, jd_text, jd_lookup_id, job_title, level or resolved_level, limit_p2,
                )
                for i, item in enumerate(result["questions"][:limit_p2]):
                    k = str(i + start_idx).zfill(2)
                    generated_meta[k] = {
                        "text": item["question"],
                        "type": item["type"],
                        "anchor_mode": item["anchor_mode"],
                        "competency_id": item["competency_id"],
                    }
            except Exception as e:
                print(f"[Prep] Competency questions error: {e}")

    if not generated_meta and limit_p2 > 0:
        # AI thất bại hoàn toàn (không có CV, chưa cấu hình API key, hoặc lỗi
        # mạng) — dự phòng bằng câu hỏi tổng quát cố định thay vì để trống Phần 2.
        start_idx = len(q_texts) + 1
        fallback_texts = [
            _DEFAULT_EXPERIENCE["q07"],
            _DEFAULT_EXPERIENCE["q08"],
        ]
        attempts = 0
        while len(fallback_texts) < limit_p2 and attempts < limit_p2 * 4:
            fallback_texts = _dedupe_questions(fallback_texts)
            if len(fallback_texts) >= limit_p2:
                break
            fallback_texts.append(_jd_gap_question(job_title, jd_text, len(fallback_texts) + attempts))
            attempts += 1
        fallback_texts = _dedupe_questions(fallback_texts)
        for i, text in enumerate(fallback_texts[:limit_p2]):
            k = str(start_idx + i).zfill(2)
            generated_meta[k] = {
                "text": text,
                "type": _infer_generated_question_type(text),
                "anchor_mode": "transfer",
                "competency_id": "",
            }

    for k, meta in generated_meta.items():
        q_texts[k] = meta["text"]

    intro_file = f"intro_{position_id}.mp3"
    audio_map = {k: _audio_filename(text) for k, text in q_texts.items()}

    try:
        import shutil

        dst_intro = QUESTION_AUDIO_DIR / intro_file
        if not dst_intro.exists() or dst_intro.stat().st_size <= 512:
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
                    if not dst.exists() or dst.stat().st_size <= 512:
                        src = gen_audio_dir / src_name
                        if src.exists():
                            shutil.copy2(src, dst)
                        else:
                            print(f"[Prep] Thiếu audio gốc: {src}")

        # Ensure all questions have TTS audio
        import asyncio

        sem = asyncio.Semaphore(3) # Limit concurrency to avoid Edge TTS rate limits

        async def _safe_tts(k, text, dst):
            async with sem:
                if not dst.exists() or dst.stat().st_size <= 512:
                    try:
                        await _tts(text, dst)
                    except Exception as e:
                        print(f"[Prep] Q{k} TTS error: {e}")

        tts_tasks = []
        for k, text in q_texts.items():
            dst = QUESTION_AUDIO_DIR / audio_map[k]
            tts_tasks.append(_safe_tts(k, text, dst))

        if tts_tasks:
            await asyncio.gather(*tts_tasks)

        print(f"[Prep] Hoàn tất chuẩn bị audio cho {prep_id}")
    except Exception as e:
        print(f"[Prep] TTS error: {e}")

    questions = {}
    for n, text in q_texts.items():
        meta = generated_meta.get(n)
        is_generated = meta is not None
        qtype = meta["type"] if meta else _question_type_for_prep(n, text, False)
        questions[n] = {
            "text":            text,
            "audio_url":       f"/audio/{audio_map[n]}",
            "type":            qtype,
            "is_generated":    is_generated,
            "allow_follow_up": qtype in _FOLLOW_UP_ELIGIBLE_TYPES,
            "anchor_mode":     meta["anchor_mode"] if meta else None,
            "competency_id":   meta["competency_id"] if meta else None,
        }

    result = {
        "prep_id":         prep_id,
        "intro_audio":     f"/audio/{intro_file}",
        "questions":       questions,
        "follow_up_limit": limit_p3,
    }

    with db() as conn:
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, created_at, questions_json, prep_status, prep_error)"
            " VALUES (?,?,?,?,?,?,?,?,NULL)"
            " ON CONFLICT(id) DO UPDATE SET questions_json=excluded.questions_json, prep_status=excluded.prep_status, prep_error=NULL",
            (prep_id, app_ref, position_id, "", "", now, json.dumps(result, ensure_ascii=False), "ready"),
        )

    return result


async def _run_prep_generation(prep_id: str, position_id: str, app_ref: str, level: str) -> None:
    """Chạy _create_prep trong background task, ghi kết quả (hoặc lỗi) vào đúng
    dòng placeholder prep_id đã tạo sẵn (prep_status='generating'). Dùng khi
    ứng viên là người đầu tiên kích hoạt tạo bộ đề — trả lời ngay cho request
    HTTP thay vì bắt ứng viên chờ suốt quá trình gọi CV/LLM/TTS."""
    try:
        await _create_prep(position_id, app_ref, level=level, prep_id=prep_id)
    except Exception as e:
        print(f"[Prep] Sinh bộ đề nền thất bại cho {prep_id}: {e}")
        with db() as conn:
            conn.execute(
                "UPDATE interview_prep SET prep_status='error', prep_error=? WHERE id=?",
                (str(e)[:500], prep_id),
            )


def _prep_from_row(row) -> dict:
    """Trả về bộ đề của prep. Prep tạo bởi _create_prep có toàn bộ nội dung đã
    đóng băng trong questions_json — đọc thẳng, không dựng lại từ đĩa. Prep tạo
    trước khi có cột này, hoặc prep khung dùng cho phỏng vấn lại (xem
    admin.request_reinterview), dùng đường dựng lại như trước."""
    row_dict = dict(row)
    raw = row_dict.get("questions_json")
    if raw:
        try:
            data = json.loads(raw)
            if data and data.get("questions"):
                return data
        except Exception:
            pass
    return _prep_from_row_legacy(row)


def _prep_from_row_legacy(row) -> dict:
    """Dựng lại bộ đề từ file .md + QUESTIONS_BANK + các cột rời rạc cũ
    (generated_questions/edited_questions/q07_text/q08_text). Giữ nguyên hành vi
    lịch sử cho các prep tạo trước khi có questions_json — KHÔNG dùng cho prep
    mới, vì đây chính là đường đọc-lại-mỗi-lần từng gây trôi đề so với audio."""
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
                except Exception:
                    pass

    md_path, _ = _find_position_files(pos)
    q0106   = _parse_q0306(md_path) if md_path else {}
    if not q0106:
        q0106 = dict(_FALLBACK_PART1_QUESTIONS)

    if len(q0106) > limit_p1:
        q0106 = dict(list(q0106.items())[:limit_p1])
    elif len(q0106) < limit_p1:
        for k, v in QUESTIONS_BANK.items():
            if len(q0106) >= limit_p1:
                break
            if not v.get("is_dynamic") and v["text"] not in q0106.values():
                new_k = str(len(q0106) + 1).zfill(2)
                q0106[new_k] = v["text"]

    q_texts = dict(q0106)

    generated_qs = {}
    if "generated_questions" in row.keys() and row["generated_questions"]:
        try:
            generated_qs = json.loads(row["generated_questions"])
        except Exception:
            pass

    row_dict = dict(row)
    if not generated_qs:
        if row_dict.get("q07_text"): generated_qs["07"] = row_dict["q07_text"]
        if row_dict.get("q08_text"): generated_qs["08"] = row_dict["q08_text"]

    edited_qs = {}
    if "edited_questions" in row.keys() and row["edited_questions"]:
        try:
            edited_qs = json.loads(row["edited_questions"]) or {}
        except Exception:
            pass

    if len(generated_qs) > limit_p2:
        generated_qs = dict(
            sorted(generated_qs.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999)[:limit_p2]
        )

    for k, v in generated_qs.items():
        q_texts[k] = v
    for k, v in edited_qs.items():
        if str(v).strip():
            q_texts[str(k)] = str(v).strip()

    audio_map = {}
    for k in q_texts:
        if k not in generated_qs and k not in edited_qs:
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
                "allow_follow_up": _question_type_for_prep(n, q_texts[n], n in generated_qs) in _FOLLOW_UP_ELIGIBLE_TYPES,
            }
            for n in q_texts if q_texts[n]
        },
        "follow_up_limit": limit_p3
    }
