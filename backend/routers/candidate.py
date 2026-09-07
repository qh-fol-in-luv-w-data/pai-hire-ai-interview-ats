import json
import asyncio
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from backend.database import db
from backend.security import bounded_text
from backend.services.candidate_access import require_access as require_reply_access
from backend.services.rate_limit import enforce as rate_limit_enforce

router = APIRouter()


def _clamp_score_adjustment(value) -> float:
    """Ép score_adjustment do AI trả về vào đúng khoảng [-1.0, 1.0].

    Prompt chỉ mô tả khoảng này bằng văn bản — không có gì ràng buộc con số
    Gemini/GPT thực sự trả về, nên một câu trả lời bị thao túng (prompt
    injection) có thể khiến model trả về giá trị lớn bất thường. Chỉ clamp
    riêng số điều chỉnh — tổng điểm cuối vẫn được clamp về [1,5] riêng.
    """
    try:
        value = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, value))


async def _analyze_candidate_reply_background(ref: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id=?", (ref,)
        ).fetchone()
    if not row:
        return

    row_dict = dict(row)
    score_bd = json.loads(row_dict.get("score_breakdown") or "{}")
    reply_text = score_bd.get("candidate_reply") or ""
    deep_qs = score_bd.get("deep_questions", [])
    if not reply_text or not deep_qs:
        return

    try:
        from backend.services.ai_service import analyze_candidate_reply
        from backend.services.document_service import extract_cv_text, get_jd_content
        from backend.config import BASE_DIR

        cv_text = ""
        if row_dict.get("cv_path"):
            cv_text = extract_cv_text(BASE_DIR / row_dict["cv_path"])
        jd_text = get_jd_content(row_dict["job_id"])

        reply_analysis = await asyncio.wait_for(
            analyze_candidate_reply(cv_text, jd_text, deep_qs, reply_text),
            timeout=45,
        )
    except Exception as e:
        print(f"[CandidateReply] AI background error for {ref}: {e}")
        reply_analysis = {
            "evaluation": "Ứng viên đã trả lời câu hỏi bổ sung. AI chưa phân tích được, cần HR xem thủ công.",
            "summary": "Ứng viên đã trả lời câu hỏi bổ sung. Cần HR xem thủ công.",
            "red_flags": [],
            "strengths": [],
            "recommendation": "Cần thảo luận thêm",
        }

    with db() as conn:
        current = conn.execute(
            "SELECT cv_score, score_breakdown FROM cv_applications WHERE id=?", (ref,)
        ).fetchone()
    if not current:
        return
    current_score = json.loads(current["score_breakdown"] or "{}")
    old_cv_score = current["cv_score"] or 0.0
    if old_cv_score > 5:
        old_cv_score = old_cv_score / 2.0

    if current_score.get("candidate_reply") != reply_text:
        print(f"[CandidateReply] {ref} analysis skipped; reply changed")
        return

    current_score["reply_analysis"] = reply_analysis
    new_status = (
        "pending_hr_approval_passed"
        if reply_analysis.get("recommendation") == "Phê duyệt"
        else "pending_hr_approval_failed"
    )

    # Re-score CV
    score_adj = _clamp_score_adjustment(reply_analysis.get("score_adjustment"))
    new_cv_score = old_cv_score + score_adj
    new_cv_score = max(1.0, min(5.0, new_cv_score))
    if not reply_analysis.get("score_adjustment_reason"):
        if score_adj > 0:
            fallback_reason = "Ứng viên bổ sung câu trả lời tốt hơn kỳ vọng, làm rõ thêm năng lực/kinh nghiệm còn thiếu trong CV."
        elif score_adj < 0:
            fallback_reason = "Câu trả lời bổ sung chưa làm rõ được các nghi vấn quan trọng hoặc phát sinh rủi ro so với CV/JD."
        else:
            fallback_reason = "Câu trả lời bổ sung không làm thay đổi đáng kể mức độ phù hợp đã đánh giá ban đầu."
        reply_analysis["score_adjustment_reason"] = reply_analysis.get("evaluation") or reply_analysis.get("summary") or fallback_reason
    reply_analysis["score_before"] = round(old_cv_score, 2)
    reply_analysis["score_adjustment"] = round(score_adj, 2)
    reply_analysis["score_after"] = round(new_cv_score, 2)
    reply_analysis["decision_before"] = (
        "CV đạt, cần ứng viên bổ sung" if (row_dict.get("status") or "").endswith("_passed") else "CV chưa đạt, cần ứng viên bổ sung"
    )
    reply_analysis["decision_after"] = "Đề xuất phê duyệt" if new_status.endswith("_passed") else "Đề xuất từ chối"
    current_score["reply_analysis"] = reply_analysis

    with db() as conn:
        conn.execute(
            "UPDATE cv_applications SET cv_score=?, score_breakdown=?, status=? WHERE id=?",
            (new_cv_score, json.dumps(current_score, ensure_ascii=False), new_status, ref),
        )
    print(f"[CandidateReply] {ref} analysis -> {new_status} | CV Score {old_cv_score} -> {new_cv_score}")


@router.get("/candidate/questions")
def get_candidate_questions(ref: str, token: str, request: Request):
    """Trả về danh sách câu hỏi phụ cho ứng viên (dùng cho trang web).

    `ref` là mã hồ sơ, không phải bí mật — bắt buộc kèm `token` (chỉ có trong
    link email gửi cho đúng ứng viên) để tránh người khác xem/nộp hộ câu trả
    lời chỉ bằng cách đoán hoặc nhìn thấy `ref`.
    """
    rate_limit_enforce(request, "candidate_questions", limit=20, window_seconds=60)
    require_reply_access(ref, token)
    with db() as conn:
        row = conn.execute(
            "SELECT name, job_id, score_breakdown, status FROM cv_applications WHERE id=?",
            (ref,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ")

    score_bd = json.loads(row["score_breakdown"] or "{}")
    deep_qs = score_bd.get("deep_questions", [])

    if not deep_qs:
        raise HTTPException(404, "Không có câu hỏi nào cần trả lời")

    already_replied = bool(score_bd.get("candidate_reply"))
    return JSONResponse({
        "name": row["name"],
        "job_id": row["job_id"],
        "questions": [{"question_text": q} if isinstance(q, str) else q for q in deep_qs],
        "already_replied": already_replied
    })


@router.post("/candidate/submit_reply")
async def submit_candidate_reply(request: Request, background: BackgroundTasks):
    """Nhận câu trả lời từ ứng viên qua form web, chấm điểm và cập nhật DB."""
    rate_limit_enforce(request, "candidate_submit_reply", limit=10, window_seconds=60)
    body = await request.json()
    ref = body.get("ref")
    token = body.get("token")
    answers = body.get("answers", [])

    if not ref:
        raise HTTPException(400, "Thiếu ref")
    require_reply_access(ref, token)

    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id=?", (ref,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ")

    row_dict = dict(row)
    score_bd = json.loads(row_dict.get("score_breakdown") or "{}")
    deep_qs = score_bd.get("deep_questions", [])

    if not deep_qs:
        raise HTTPException(400, "Hồ sơ này không có câu hỏi nào cần trả lời")

    if score_bd.get("candidate_reply"):
        return JSONResponse({"ok": True, "already_done": True, "msg": "Câu trả lời của bạn đã được ghi nhận trước đó."})

    reply_parts = []
    for i, q in enumerate(deep_qs):
        ans = answers[i] if i < len(answers) else ""
        ans = bounded_text(str(ans), f"answers[{i}]", 5000)
        q_text = q.get('question_text', '') if isinstance(q, dict) else str(q)
        reply_parts.append(f"Câu {i+1}: {q_text}\nTrả lời: {ans}")
    reply_text = "\n\n".join(reply_parts)

    pending_score = row_dict.get("cv_score") or 0
    if pending_score > 5:
        pending_score = pending_score / 2.0
    score_bd["candidate_reply"] = reply_text
    score_bd["reply_analysis"] = {
        "summary": "Ứng viên đã gửi câu trả lời. Hệ thống đang phân tích tự động.",
        "recommendation": "Đang phân tích",
        "score_before": pending_score,
        "score_adjustment": 0,
        "score_after": pending_score,
        "decision_before": "Đang chờ ứng viên bổ sung",
        "decision_after": "Đang phân tích",
    }
    previous_status = row_dict.get("status") or ""
    new_status = "pending_hr_approval_passed" if previous_status.endswith("_passed") else "pending_hr_approval_failed"

    with db() as conn:
        conn.execute(
            "UPDATE cv_applications SET score_breakdown=?, status=? WHERE id=?",
            (json.dumps(score_bd, ensure_ascii=False), new_status, ref)
        )

    background.add_task(_analyze_candidate_reply_background, ref)
    print(f"[CandidateReply] {ref} saved -> {new_status}")
    return JSONResponse({"ok": True, "recommendation": "Đang phân tích"})
