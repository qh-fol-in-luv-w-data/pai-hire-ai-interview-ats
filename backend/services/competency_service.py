import hashlib
import json
import re
import time
import uuid

from backend.database import db

_VALID_ANCHOR_MODES = {"probe", "transfer"}
_VALID_QUESTION_TYPES = {"Technical", "Experience", "Soft Skill"}
_VALID_COVERAGE = {"high", "medium", "low"}


async def extract_jd_competencies(job_id: str | None, jd_text: str) -> list[dict]:
    """Trích năng lực CỐT LÕI từ JD bằng LLM. Cache theo job_id + nội dung JD
    (không phụ thuộc ứng viên) vì JD không đổi giữa các ứng viên cùng vị trí.
    job_id=None (vd: JD dán tự do qua webhook bên thứ 3) thì không cache."""
    jd_text = (jd_text or "").strip()
    if not jd_text:
        return []

    jd_hash = hashlib.sha1(jd_text.encode("utf-8")).hexdigest()[:16]

    if job_id:
        with db() as conn:
            row = conn.execute(
                "SELECT competencies_json FROM jd_competencies WHERE job_id=? AND jd_hash=?",
                (job_id, jd_hash),
            ).fetchone()
        if row and row["competencies_json"]:
            try:
                cached = json.loads(row["competencies_json"])
                if cached:
                    return cached
            except Exception:
                pass

    from backend.config import OPENAI_API_KEY, COMPETENCY_EXTRACTION_PROMPT
    if not OPENAI_API_KEY:
        return []

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = COMPETENCY_EXTRACTION_PROMPT.format(jd_text=jd_text[:6000])
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=700,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    parsed = json.loads(raw)
    raw_items = parsed.get("competencies", []) if isinstance(parsed, dict) else []

    cleaned: list[dict] = []
    seen_ids = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        cid = re.sub(r"[^a-z0-9_]", "", str(item.get("id") or "").strip().lower().replace(" ", "_"))
        label = str(item.get("label") or "").strip()
        if not cid or not label or cid in seen_ids:
            continue
        try:
            weight = int(item.get("weight") or 2)
        except (TypeError, ValueError):
            weight = 2
        weight = max(1, min(3, weight))
        cleaned.append({"id": cid, "label": label, "weight": weight})
        seen_ids.add(cid)

    if cleaned and job_id:
        with db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO jd_competencies (id, job_id, jd_hash, competencies_json, created_at) VALUES (?,?,?,?,?)",
                (
                    f"COMP-{uuid.uuid4().hex[:10].upper()}",
                    job_id,
                    jd_hash,
                    json.dumps(cleaned, ensure_ascii=False),
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                ),
            )
    return cleaned


async def generate_competency_questions(
    cv_text: str,
    jd_text: str,
    job_id: str | None,
    position: str,
    level: str,
    num_gen: int,
) -> dict:
    """Sinh câu hỏi ràng buộc theo năng lực JD: PROBE nếu CV có bằng chứng cụ thể,
    TRANSFER nếu không. Độ phủ JD được bảo đảm bằng cấu trúc (mỗi năng lực được xét
    riêng), không phải bằng bộ lọc hậu kiểm. Dùng chung cho luồng tạo bộ đề phỏng vấn
    và luồng câu hỏi bổ sung qua email.

    Trả về {"coverage": "high"|"medium"|"low", "questions": [
        {"question", "anchor_mode", "type", "competency_id"}
    ]}. coverage="medium" và questions=[] khi không đủ dữ kiện để sinh (thiếu JD,
    thiếu CV, hoặc chưa cấu hình OPENAI_API_KEY) — gọi nơi dùng tự quyết định
    fallback phù hợp với ngữ cảnh của mình.
    """
    empty = {"coverage": "medium", "questions": []}
    if num_gen <= 0:
        return empty

    competencies = await extract_jd_competencies(job_id, jd_text)
    if not competencies:
        return empty

    from backend.config import OPENAI_API_KEY, COMPETENCY_QUESTIONS_PROMPT
    if not OPENAI_API_KEY or not (cv_text or "").strip():
        return empty

    competency_list = "\n".join(
        f"- [{c['id']}] {c['label']} (mức độ quan trọng: {c['weight']}/3)" for c in competencies
    )
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = COMPETENCY_QUESTIONS_PROMPT.format(
        position=position or "vị trí đang tuyển",
        level=level or "Junior",
        competency_list=competency_list,
        cv_text=cv_text[:4000],
        num_gen=num_gen,
    )
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=max(1000, num_gen * 200),
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    parsed = json.loads(raw)

    coverage = "medium"
    raw_items = []
    if isinstance(parsed, dict):
        coverage = str(parsed.get("coverage") or "medium").strip().lower()
        if coverage not in _VALID_COVERAGE:
            coverage = "medium"
        raw_items = parsed.get("questions", [])

    valid_ids = {c["id"] for c in competencies}
    questions = []
    seen_signatures = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("question") or "").strip()
        if not text:
            continue
        signature = re.sub(r"\s+", " ", text.lower())[:120]
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        anchor_mode = str(item.get("anchor_mode") or "").strip().lower()
        if anchor_mode not in _VALID_ANCHOR_MODES:
            anchor_mode = "transfer"

        qtype = str(item.get("type") or "").strip()
        if qtype not in _VALID_QUESTION_TYPES:
            qtype = "Experience"

        competency_id = str(item.get("competency_id") or "").strip()
        if competency_id not in valid_ids:
            competency_id = ""

        questions.append({
            "question": text,
            "anchor_mode": anchor_mode,
            "type": qtype,
            "competency_id": competency_id,
        })

    return {"coverage": coverage, "questions": questions[:num_gen]}
