import os
import re
import uuid
import time
import json
import httpx
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, BackgroundTasks, File, Form, UploadFile, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from backend.database import db, log_application_event
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS, _JOB_LEVELS, INTERVIEW_URL
from backend.routers.api_v1 import parse_slot_datetime

from backend.services.email_service import send_interview_result, send_reinterview_email
from backend.routers.auth import _group_consecutive_alerts
router = APIRouter()


def _interview_average_score(answer_rows):
    """Score a question group without letting a weaker follow-up lower its base answer."""
    score_map = {"nắm vững": 10.0, "am hiểu": 7.5, "có biết qua": 5.0, "không biết": 0.0}
    groups = {}
    for answer in answer_rows:
        level = answer["ai_level"]
        if level not in score_map:
            continue
        question_number = str(answer["question_number"] or "")
        base_number = question_number.split(".", 1)[0]
        key = (answer["attempt_number"] or 1, base_number)
        group = groups.setdefault(key, {"base_score": None, "follow_up_scores": []})
        if "." in question_number:
            group["follow_up_scores"].append(score_map[level])
        else:
            group["base_score"] = score_map[level]

    group_scores = []
    for group in groups.values():
        base_score = group["base_score"]
        included = group["follow_up_scores"] if base_score is None else [
            base_score,
            *(score for score in group["follow_up_scores"] if score > base_score),
        ]
        if included:
            group_scores.append(sum(included) / len(included))
    return round(sum(group_scores) / len(group_scores), 2) if group_scores else None


@router.get("/admin/accounts")
def admin_list_accounts(x_admin_key: str = Header(None)):
    """Main admin can review existing web accounts and their access level."""
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute("""SELECT id,name,email,phone,role,created_at
            FROM users ORDER BY CASE WHEN role IN ('admin','platform_admin') THEN 0 ELSE 1 END, created_at DESC""").fetchall()
    return {"accounts": [dict(row) for row in rows]}


@router.patch("/admin/accounts/{user_id}/role")
async def admin_update_account_role(user_id: str, request: Request, x_admin_key: str = Header(None)):
    """Grant/revoke internal admin access. Platform role is never assignable here."""
    require_admin(x_admin_key)
    body = await request.json()
    role = str(body.get("role") or "").strip()
    if role not in {"candidate", "admin"}:
        raise HTTPException(422, "Chỉ có thể cấp hoặc thu hồi quyền Quản trị viên")
    with db() as conn:
        target = conn.execute("SELECT id,role FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Không tìm thấy tài khoản")
        if target["role"] == "platform_admin":
            raise HTTPException(403, "Không thể thay đổi quyền quản trị nền tảng tại đây")
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        # Role changes take effect immediately: old sessions cannot retain a
        # permission that has just been revoked.
        conn.execute("UPDATE user_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (int(time.time()), user_id))
    return {"success": True, "role": role}


def _normalize_cv_score_value(value):
    if value is None:
        return None
    try:
        score = float(value)
    except Exception:
        return value
    return round(score / 2, 1) if score > 5 else round(score, 1)


def _row_logs(rows):
    logs = []
    for r in rows:
        item = dict(r)
        if item.get("details"):
            try:
                item["details"] = json.loads(item["details"])
            except Exception:
                pass
        logs.append(item)
    return logs


def _fallback_application_logs(app_row, prep_row, interview_rows):
    app = dict(app_row)
    logs = [{
        "app_id": app.get("id"),
        "email": app.get("email"),
        "event_type": "application_submitted",
        "message": f"Ứng viên nộp hồ sơ cho vị trí {app.get('job_id') or '—'}.",
        "details": {"status": app.get("status")},
        "created_at": app.get("applied_at"),
    }]
    if app.get("cv_score") is not None:
        logs.append({
            "app_id": app.get("id"),
            "email": app.get("email"),
            "event_type": "cv_scored",
            "message": f"AI đã đánh giá hồ sơ: {_normalize_cv_score_value(app.get('cv_score'))}/5.",
            "details": {"status": app.get("status")},
            "created_at": app.get("applied_at"),
        })
    if prep_row:
        logs.append({
            "app_id": app.get("id"),
            "email": app.get("email"),
            "event_type": "questions_ready",
            "message": "Đã tạo bộ câu hỏi phỏng vấn.",
            "details": {"prep_id": prep_row["id"]},
            "created_at": prep_row["created_at"],
        })
    for iv in interview_rows:
        logs.append({
            "app_id": app.get("id"),
            "email": app.get("email"),
            "event_type": "interview_submitted",
            "message": f"Ứng viên đã nộp bài phỏng vấn {iv['id']}.",
            "details": {"interview_id": iv["id"], "status": iv["status"]},
            "created_at": iv["submitted_at"],
        })
    return sorted(logs, key=lambda x: x.get("created_at") or "", reverse=True)

@router.get("/admin/settings")
def get_settings(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {row["key"]: row["value"] for row in rows}
    try:
        cv_pass_score = float(settings.get("cv_pass_score", PASS_SCORE))
        if cv_pass_score > 5:
            cv_pass_score = cv_pass_score / 2
        settings["cv_pass_score"] = str(cv_pass_score)
    except Exception:
        settings["cv_pass_score"] = str(PASS_SCORE)
    return JSONResponse(settings)

@router.post("/admin/settings")
async def update_settings(request: Request, x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    body = await request.json()
    with db() as conn:
        for k, v in body.items():
            if k == "cv_pass_score":
                try:
                    v = float(v)
                    if v > 5:
                        v = v / 2
                except Exception:
                    v = PASS_SCORE
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                (k, str(v), str(v))
            )
    return JSONResponse({"status": "ok"})

@router.get("/admin/interviews")
def admin_list_interviews(
    status: str = None,
    position_id: str = None,
    level: str = None,
    limit: int = 100,
    offset: int = 0,
    x_admin_key: str = Header(None),
):
    require_admin(x_admin_key)

    where, params = [], []
    if status:
        where.append("i.status = ?");      params.append(status)
    if position_id:
        where.append("i.position_id = ?"); params.append(position_id)
    if level:
        where.append("(i.level = ? OR i.position_id LIKE ?)")
        params.extend([level, f"{level}_%"])

    # No filter must produce no WHERE clause; a bare `WHERE GROUP BY` is
    # invalid SQLite and breaks the default interview list request.
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(f"""
            SELECT i.id, i.candidate_id, CASE WHEN ca.application_source='api' THEN '' ELSE i.position_id END AS position_id, i.status, i.submitted_at,
                   i.level, i.is_reapplicant, i.reinterview_of, i.cv_path,
                   CASE WHEN i.hod_questions IS NOT NULL AND i.hod_questions != '' THEN 1 ELSE 0 END as has_hod_questions,
                   c.name as candidate_name, c.email as candidate_email,
                   ca.application_source,
                   COUNT(a.id) as answer_count,
                   (
                     SELECT ROUND(AVG(group_score), 1)
                     FROM (
                       SELECT AVG(CASE ax.ai_level
                         WHEN 'nắm vững'    THEN 10.0
                         WHEN 'am hiểu'     THEN 7.5
                         WHEN 'có biết qua' THEN 5.0
                         WHEN 'không biết'  THEN 0.0
                         ELSE NULL END) AS group_score
                       FROM answers ax
                       WHERE ax.interview_id = i.id
                       GROUP BY ax.attempt_number,
                         CASE
                           WHEN instr(ax.question_number, '.') > 0 THEN substr(ax.question_number, 1, instr(ax.question_number, '.') - 1)
                           ELSE ax.question_number
                         END
                     )
                   ) as avg_score
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            LEFT JOIN interview_prep ip ON ip.id = i.prep_id
            LEFT JOIN cv_applications ca ON ca.id = ip.app_ref
            {clause}
            GROUP BY i.id
            ORDER BY i.submitted_at DESC
            LIMIT ? OFFSET ?
        """, (*params, limit, offset)).fetchall()
        interview_ids = [row["id"] for row in rows]
        answer_rows = conn.execute(
            f"SELECT interview_id, question_number, ai_level, attempt_number FROM answers WHERE interview_id IN ({','.join('?' for _ in interview_ids)})",
            interview_ids,
        ).fetchall() if interview_ids else []

    answers_by_interview = {}
    for answer in answer_rows:
        answers_by_interview.setdefault(answer["interview_id"], []).append(answer)
    interviews = [dict(row) for row in rows]
    for interview in interviews:
        interview["avg_score"] = _interview_average_score(answers_by_interview.get(interview["id"], []))
    return {"total": len(rows), "interviews": interviews}


@router.patch("/interview/{interview_id}/review")
async def review_interview(interview_id: str, body: dict, x_admin_key: str = Header(None)):
    """
    body: {
      "status": "reviewed" | "passed" | "failed",
      "answers": { "01": { "score": 8, "notes": "..." }, ... }
    }
    §27 — Khi status=passed/failed → tự động gửi email kết quả cho ứng viên.
    """
    require_admin(x_admin_key)
    new_status = body.get("status", "reviewed")
    if new_status not in {"reviewed", "passed", "failed"}:
        raise HTTPException(400, "Trạng thái review không hợp lệ")
    hr_score = body.get("hr_score")
    hr_notes = body.get("hr_notes")
    expert_score = body.get("expert_score")
    expert_notes = body.get("expert_notes")

    with db() as conn:
        conn.execute(
            "UPDATE interviews SET status = ?, hr_score = ?, hr_notes = ?, expert_score = ?, expert_notes = ? WHERE id = ?",
            (new_status, hr_score, hr_notes, expert_score, expert_notes, interview_id)
        )
        for qn, review in body.get("answers", {}).items():
            conn.execute("""
                UPDATE answers SET score = ?, notes = ?
                WHERE interview_id = ? AND question_number = ?
            """, (review.get("score"), review.get("notes"), interview_id, qn))

    return {"ok": True, "interview_id": interview_id, "status": new_status}


@router.post("/interview/{interview_id}/send-result-email")
def api_send_result_email(interview_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute("""
            SELECT c.name, c.email, i.position_id, i.status, i.id as iv_id
            FROM interviews i
            LEFT JOIN candidates c ON i.candidate_id = c.id
            WHERE i.id = ?
        """, (interview_id,)).fetchone()
        
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        if row["status"] not in ("passed", "failed"):
            raise HTTPException(400, "Chỉ gửi email khi trạng thái là Đạt hoặc Không đạt")
            
        candidate_email = row["email"]
        candidate_name = row["name"] or "Ứng viên"
        
        if not candidate_email:
            # Fallback
            _app = conn.execute("SELECT id, email, name FROM cv_applications WHERE id = (SELECT candidate_id FROM interviews WHERE id=?)", (interview_id,)).fetchone()
            if _app:
                candidate_email = _app["email"]
                if not row["name"]: candidate_name = _app["name"] or "Ứng viên"
                
        if not candidate_email:
            raise HTTPException(400, "Không tìm thấy email ứng viên")

        send_interview_result(
            candidate_name,
            candidate_email,
            row["position_id"],
            row["status"],
            interview_id,
        )
    return {"ok": True, "msg": "Đã gửi email thành công tới " + candidate_email}


@router.get("/admin/applications")
def admin_list_applications(
    status:  str = None,
    job_id:  str = None,
    limit:   int = 100,
    _auth=   None,
    x_admin_key: str = Header(None),
):
    require_admin(x_admin_key)
    # Main ATS list is exclusively website Apply submissions. API tenants
    # have their own queue under /admin/companies/api-applications.
    where, params = ["COALESCE(application_source,'') != 'api'", "LOWER(COALESCE(job_id,'')) NOT GLOB 'jd_*'"], []
    if status:
        where.append("status = ?");  params.append(status)
    if job_id:
        where.append("job_id = ?");  params.append(job_id)
    clause = "WHERE " + " AND ".join(where)

    with db() as conn:
        rows = conn.execute(
            f"""SELECT a.*,
                   (
                     SELECT i.status
                     FROM interviews i
                     JOIN interview_prep p ON p.id=i.prep_id
                     WHERE p.app_ref=a.id
                     ORDER BY COALESCE(i.submitted_at, '') DESC, i.id DESC
                     LIMIT 1
                   ) AS latest_interview_status
                 FROM cv_applications a {clause} ORDER BY a.applied_at DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
        prep_refs = {
            r["app_ref"]
            for r in conn.execute(
                "SELECT DISTINCT app_ref FROM interview_prep WHERE app_ref IS NOT NULL AND app_ref != ''"
            ).fetchall()
        }

    applications = [dict(r) for r in rows]
    for app in applications:
        if app.get("application_source") == "api" or str(app.get("job_id") or "").lower().startswith("jd_"):
            app["job_id"] = "-"
        app["cv_score"] = _normalize_cv_score_value(app.get("cv_score"))
        app["question_prep_status"] = app.get("prep_status") or ("ready" if app.get("id") in prep_refs else "none")
    return {"total": len(rows), "applications": applications}


@router.get("/admin/applications/{app_id}")
def admin_get_application(app_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
        prep_row = conn.execute(
            "SELECT * FROM interview_prep WHERE app_ref=? ORDER BY created_at DESC LIMIT 1",
            (app_id,),
        ).fetchone()
        log_rows = []
        interview_rows = []
        if row:
            log_rows = conn.execute(
                """
                SELECT * FROM application_logs
                WHERE LOWER(email)=LOWER(?) OR app_id=?
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (row["email"], app_id),
            ).fetchall()
            interview_rows = conn.execute(
                """
                SELECT DISTINCT i.id, i.status, i.submitted_at
                FROM interviews i
                LEFT JOIN candidates c ON c.id=i.candidate_id
                LEFT JOIN interview_prep p ON p.id=i.prep_id
                WHERE LOWER(c.email)=LOWER(?) OR p.app_ref=?
                ORDER BY i.submitted_at DESC
                LIMIT 50
                """,
                (row["email"], app_id),
            ).fetchall()
    if not row:
        raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
    data = dict(row)
    if data.get("application_source") == "api" or str(data.get("job_id") or "").lower().startswith("jd_"):
        data["job_id"] = "-"
    data["cv_score"] = _normalize_cv_score_value(data.get("cv_score"))
    if data.get("cv_extracted_info"):
        try:
            data["cv_extracted_info"] = json.loads(data["cv_extracted_info"])
        except Exception:
            pass
    if data.get("score_breakdown"):
        try:
            data["score_breakdown"] = json.loads(data["score_breakdown"])
        except (TypeError, json.JSONDecodeError):
            # Dữ liệu cũ có thể lưu breakdown không đúng JSON; vẫn phải mở được hồ sơ.
            data["score_breakdown"] = {}
    if data.get("interview_config"):
        try:
            data["interview_config"] = json.loads(data["interview_config"])
        except (TypeError, json.JSONDecodeError):
            data["interview_config"] = {}
    data["application_logs"] = _row_logs(log_rows) if log_rows else _fallback_application_logs(row, prep_row, interview_rows)
    data["question_prep_status"] = data.get("prep_status") or ("ready" if prep_row else "none")
    if prep_row:
        from backend.services.prep_service import _prep_from_row
        prep = _prep_from_row(prep_row)
        questions_preview = []
        for q_num, q_data in (prep.get("questions") or {}).items():
            meta = QUESTIONS_BANK.get(q_num, {})
            is_generated = bool(q_data.get("is_generated"))
            questions_preview.append({
                "n": q_num,
                "text": q_data.get("text", ""),
                "audio_url": q_data.get("audio_url", ""),
                "type": q_data.get("type") or meta.get("type", ""),
                "label": meta.get("label", f"Câu {q_num}"),
                "is_ai_generated": is_generated,
            })
        data["interview_prep"] = {
            "prep_id": prep.get("prep_id"),
            "position_id": prep_row["position_id"],
            "created_at": prep_row["created_at"],
            "questions": questions_preview,
            "follow_up_limit": prep.get("follow_up_limit", 0),
        }
    return data


@router.get("/admin/proctoring/logs")
def admin_get_proctoring_logs(
    app_id: str = None,
    interview_id: str = None,
    x_admin_key: str = Header(None),
):
    require_admin(x_admin_key)
    with db() as conn:
        resolved_app_id = app_id
        tab_switches = 0
        if interview_id:
            iv = conn.execute(
                "SELECT id, cv_path, tab_switches FROM interviews WHERE id=?",
                (interview_id,),
            ).fetchone()
            if iv:
                tab_switches = iv["tab_switches"] or 0
                if not resolved_app_id and iv["cv_path"]:
                    m = re.search(r"APP-[A-F0-9]{8}", iv["cv_path"])
                    if m:
                        resolved_app_id = m.group(0)

        alerts = []
        if resolved_app_id:
            session_row = conn.execute(
                """
                SELECT session_id, MAX(id) AS latest_id
                FROM proctoring_alerts
                WHERE session_id=? OR session_id LIKE ?
                GROUP BY session_id
                ORDER BY latest_id DESC
                LIMIT 1
                """,
                (resolved_app_id, f"{resolved_app_id}:%"),
            ).fetchone()
            session_id = session_row["session_id"] if session_row else None
            alerts = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, session_id, alert_type, snapshot_id, timestamp, created_at
                    FROM proctoring_alerts
                    WHERE session_id=?
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            ] if session_id else []

    return {
        "app_id": resolved_app_id,
        "interview_id": interview_id,
        "tab_switches": tab_switches,
        "proctoring_alerts": alerts,
    }

@router.post("/admin/applications/{app_id}/analyze-reply")
async def admin_analyze_reply(app_id: str, request: Request, x_admin_key: str = Header(None)):
    """API cho HR nhập câu trả lời của ứng viên qua email để AI phân tích."""
    require_admin(x_admin_key)
    
    try:
        body = await request.json()
        reply_text = body.get("reply_text", "").strip()
        if not reply_text:
            raise HTTPException(400, "Nội dung trả lời không được để trống")
            
        with db() as conn:
            row = conn.execute("SELECT * FROM cv_applications WHERE id = ?", (app_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy hồ sơ")
            if not row["status"].startswith("waiting_for_reply"):
                raise HTTPException(400, f"Hồ sơ đang ở trạng thái '{row['status']}', không thể phân tích phản hồi")
                
            score_bd = json.loads(row["score_breakdown"] or "{}")
            deep_qs = score_bd.get("deep_questions", [])
            
        # Analyze reply
        from backend.services.ai_service import analyze_candidate_reply
        from backend.services.document_service import extract_cv_text, get_jd_content
        import os
        from pathlib import Path
        
        cv_text = ""
        if row["cv_path"] and os.path.exists(row["cv_path"]):
            cv_text = extract_cv_text(Path(row["cv_path"]))
            
        jd_text = get_jd_content(row["job_id"])
            
        reply_analysis = await analyze_candidate_reply(cv_text, jd_text, deep_qs, reply_text)
        old_cv_score = _normalize_cv_score_value(row["cv_score"] or 0.0)
        score_adj = float(reply_analysis.get("score_adjustment") or 0.0)
        new_cv_score = max(1.0, min(5.0, old_cv_score + score_adj))
        
        # Save to DB and update status
        score_bd["candidate_reply"] = reply_text
        
        # Determine pass/fail from recommendation
        new_status = "pending_hr_approval_passed" if reply_analysis.get("recommendation") == "Phê duyệt" else "pending_hr_approval_failed"
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
            "CV đạt, cần ứng viên bổ sung" if (row["status"] or "").endswith("_passed") else "CV chưa đạt, cần ứng viên bổ sung"
        )
        reply_analysis["decision_after"] = "Đề xuất phê duyệt" if new_status.endswith("_passed") else "Đề xuất từ chối"
        score_bd["reply_analysis"] = reply_analysis
        
        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET cv_score=?, score_breakdown=?, status=? WHERE id=?",
                (new_cv_score, json.dumps(score_bd, ensure_ascii=False), new_status, app_id)
            )
        log_application_event(
            app_id,
            row["email"],
            "candidate_reply_analyzed",
            f"AI đã phân tích phản hồi bổ sung, trạng thái mới: {new_status}.",
            {"score_before": old_cv_score, "score_after": new_cv_score, "score_adjustment": score_adj},
        )
            
        return {"ok": True, "analysis": reply_analysis, "new_status": new_status}
        
    except Exception as e:
        print(f"Error analyzing reply: {e}")
        raise HTTPException(500, str(e))


@router.post("/admin/applications/{app_id}/approve")
async def admin_approve_application(app_id: str, request: Request, x_admin_key: str = Header(None)):
    """§ Feature (6): HR duyệt CV → cập nhật status=passed → gửi Email Pass với link phỏng vấn."""
    require_admin(x_admin_key)
    
    try:
        body = await request.json()
        from backend.services.prep_service import normalize_interview_config
        raw_interview_config = body.get("config") if "config" in body else None
        valid_from = body.get("valid_from")
        valid_until = body.get("valid_until")
        is_unlimited = body.get("is_unlimited", False)
    except:
        raw_interview_config = None
        valid_from = None
        valid_until = None
        is_unlimited = False
        
    from backend.services.email_service import send_pass_email
    from datetime import datetime, timezone
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
        if not row["status"].startswith("pending_hr_approval"):
            raise HTTPException(400, f"Hồ sơ đang ở trạng thái '{row['status']}', không cần duyệt lại")

        level = dict(row).get("level", "Junior") or "Junior"
        saved_config = {}
        if row["interview_config"]:
            try:
                saved_config = json.loads(row["interview_config"])
            except Exception:
                saved_config = {}
        # Cấu hình đã chọn khi tạo bộ câu hỏi là nguồn mặc định. Giao diện cũ gửi
        # is_unlimited=true khi chưa chạm vào lịch, không được phép làm mất lịch này.
        if saved_config.get("VALID_FROM") and saved_config.get("VALID_UNTIL") and is_unlimited and not valid_from and not valid_until:
            is_unlimited = False
            valid_from = saved_config.get("VALID_FROM")
            valid_until = saved_config.get("VALID_UNTIL")
        if raw_interview_config is not None:
            merged_config = dict(saved_config)
            merged_config.update(raw_interview_config)
            if not is_unlimited:
                merged_config["IS_UNLIMITED"] = False
                merged_config["VALID_FROM"] = valid_from or merged_config.get("VALID_FROM")
                merged_config["VALID_UNTIL"] = valid_until or merged_config.get("VALID_UNTIL")
            interview_config = json.dumps(normalize_interview_config(merged_config))
        else:
            interview_config = row["interview_config"]
        if raw_interview_config is None and saved_config:
            if "IS_UNLIMITED" in saved_config:
                is_unlimited = bool(saved_config.get("IS_UNLIMITED"))
            valid_from = valid_from or saved_config.get("VALID_FROM")
            valid_until = valid_until or saved_config.get("VALID_UNTIL")
        # Tạo slot
        slot_token = f"SLOT-{uuid.uuid4().hex[:12].upper()}"
        if not is_unlimited and (not valid_from or not valid_until):
            raise HTTPException(400, "Hồ sơ chưa có khung giờ phỏng vấn. Vui lòng tạo lại câu hỏi và chọn thời gian trước khi gửi email.")
        start_time = None
        end_time = None
        if not is_unlimited:
            start_dt = parse_slot_datetime(valid_from)
            end_dt = parse_slot_datetime(valid_until)
            if end_dt <= start_dt:
                raise HTTPException(400, "Giờ kết thúc phải sau giờ bắt đầu")
            start_time = start_dt.isoformat()
            end_time = end_dt.isoformat()
        conn.execute(
            "INSERT INTO interview_slots (token, app_id, position_id, level, start_time, end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (slot_token, app_id, row["job_id"], level, start_time, end_time, datetime.now(timezone.utc).isoformat())
        )
        conn.execute(
            "UPDATE cv_applications SET status='passed', interview_config=?, interview_link=?, interview_slot_token=?, interview_link_sent_at=?, interview_link_source='admin' WHERE id=?",
            (interview_config, f"{INTERVIEW_URL}?slot={slot_token}", slot_token, datetime.now(timezone.utc).isoformat(), app_id)
        )

    # Gửi email Pass
    time_note = "không giới hạn thời gian" if is_unlimited else f"từ {start_time} đến {end_time}"
    if not is_unlimited and start_time and end_time:
        try:
            st = datetime.fromisoformat(start_time).strftime("%H:%M %d/%m/%Y")
            et = datetime.fromisoformat(end_time).strftime("%H:%M %d/%m/%Y")
            time_note = f"từ {st} đến {et}"
        except:
            pass
    send_pass_email(row["name"], row["email"], row["job_id"], app_id, level=level, slot_token=slot_token, time_note=time_note)
    log_application_event(
        app_id,
        row["email"],
        "interview_email_sent",
        "Hồ sơ của bạn đã được duyệt! Chúng tôi đã gửi email mời phỏng vấn kèm link tham gia tới hộp thư của bạn — vui lòng kiểm tra email (kể cả mục Spam/Quảng cáo) để xem chi tiết và khung giờ phỏng vấn.",
        {"slot_token": slot_token, "time_note": time_note, "level": level},
    )
    print(f"[HR Approve] {app_id} → passed → Email sent to {row['email']}")
    return {"ok": True, "app_id": app_id, "status": "passed", "msg": f"Đã duyệt và gửi email mời phỏng vấn tới {row['email']}"}


@router.post("/admin/applications/{app_id}/generate_prep")
async def admin_generate_prep_preview(app_id: str, request: Request, background_tasks: BackgroundTasks, x_admin_key: str = Header(None)):
    """Tạo trước danh sách câu hỏi phỏng vấn để HR xem và duyệt trước khi gửi email."""
    require_admin(x_admin_key)
    try:
        body = await request.json()
    except:
        body = {}

    from backend.services.prep_service import _create_prep, normalize_interview_config
    
    with db() as conn:
        row = conn.execute("SELECT * FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy đơn")

    # Save config first so _create_prep respects it
    config = normalize_interview_config(body.get("config"))
    if not config.get("IS_UNLIMITED"):
        valid_from = config.get("VALID_FROM")
        valid_until = config.get("VALID_UNTIL")
        if not valid_from or not valid_until:
            raise HTTPException(400, "Vui lòng chọn thời gian bắt đầu và kết thúc truy cập link phỏng vấn")
        try:
            if parse_slot_datetime(valid_until) <= parse_slot_datetime(valid_from):
                raise HTTPException(400, "Giờ kết thúc phải sau giờ bắt đầu")
        except ValueError as exc:
            raise HTTPException(400, f"Định dạng thời gian không hợp lệ: {exc}")
    if config:
        with db() as conn:
            conn.execute(
                "UPDATE cv_applications SET interview_config=?, prep_status='generating', prep_error=NULL WHERE id=?",
                (json.dumps(config), app_id)
            )
    
    level = dict(row).get("level", "Junior") or "Junior"
    
    # Delete existing prep so we regenerate fresh
    with db() as conn:
        conn.execute("DELETE FROM interview_prep WHERE app_ref=?", (app_id,))
        
    async def run_prep_background():
        try:
            prep = await _create_prep(dict(row)["job_id"], app_id, level=level)
            with db() as conn:
                conn.execute(
                    "UPDATE cv_applications SET prep_status='ready', prep_error=NULL WHERE id=?",
                    (app_id,),
                )
            log_application_event(
                app_id,
                row["email"],
                "questions_ready",
                "Đã tạo bộ câu hỏi phỏng vấn và lưu vào hồ sơ.",
                {"prep_id": prep.get("prep_id"), "question_count": len(prep.get("questions") or {})},
            )
        except Exception as e:
            with db() as conn:
                conn.execute(
                    "UPDATE cv_applications SET prep_status='error', prep_error=? WHERE id=?",
                    (str(e), app_id),
                )
            log_application_event(app_id, row["email"], "questions_error", "Tạo câu hỏi phỏng vấn bị lỗi.", {"error": str(e)})

    background_tasks.add_task(run_prep_background)
    
    return {"ok": True, "msg": "Đang tạo bộ câu hỏi ngầm...", "prep_status": "generating"}


@router.patch("/admin/applications/{app_id}/prep")
async def admin_update_prep_questions(app_id: str, body: dict, background: BackgroundTasks, x_admin_key: str = Header(None)):
    """HR sửa trực tiếp câu hỏi đã sinh trước khi gửi link phỏng vấn."""
    require_admin(x_admin_key)
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise HTTPException(400, "Danh sách câu hỏi không hợp lệ")
    cleaned = {str(k): str(v or "").strip() for k, v in questions.items()}
    if any(not value for value in cleaned.values()):
        raise HTTPException(400, "Câu hỏi không được để trống")

    from backend.services.prep_service import _prep_from_row, _audio_filename
    from backend.config import QUESTION_AUDIO_DIR
    from backend.services.ai_service import _tts
    with db() as conn:
        app = conn.execute("SELECT id, email FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        prep = conn.execute("SELECT * FROM interview_prep WHERE app_ref=? ORDER BY created_at DESC LIMIT 1", (app_id,)).fetchone()
        if not app or not prep:
            raise HTTPException(404, "Chưa có bộ câu hỏi để chỉnh sửa")
        old_prep = _prep_from_row(prep)
        old_questions = {str(n): q.get("text", "") for n, q in (old_prep.get("questions") or {}).items()}
        changed_questions = {
            n: text for n, text in cleaned.items()
            if text != str(old_questions.get(n, "")).strip()
        }

        # Prep đóng băng (questions_json) sửa thẳng vào đó — audio_url đổi theo
        # hash nội dung mới nên không cần cache-bust thủ công. Prep cũ (chưa có
        # questions_json) giữ đường edited_questions như trước.
        is_frozen = bool(prep["questions_json"]) if "questions_json" in prep.keys() else False
        if is_frozen:
            frozen = json.loads(prep["questions_json"])
            for n, text in changed_questions.items():
                q = (frozen.get("questions") or {}).get(n)
                if not q:
                    continue
                q["text"] = text
                q["audio_url"] = f"/audio/{_audio_filename(text)}"
            conn.execute(
                "UPDATE interview_prep SET questions_json=? WHERE id=?",
                (json.dumps(frozen, ensure_ascii=False), prep["id"]),
            )
        else:
            try:
                saved_edits = json.loads(prep["edited_questions"] or "{}")
            except Exception:
                saved_edits = {}
            # Frontend chỉ gửi các câu vừa đổi. Giữ nguyên các lần sửa trước đó.
            saved_edits.update(changed_questions)
            conn.execute(
                "UPDATE interview_prep SET edited_questions=? WHERE id=?",
                (json.dumps(saved_edits, ensure_ascii=False), prep["id"]),
            )

    async def regenerate_audio():
        for n, text in changed_questions.items():
            try:
                if is_frozen:
                    await _tts(text, QUESTION_AUDIO_DIR / _audio_filename(text))
                else:
                    await _tts(text, QUESTION_AUDIO_DIR / f"{prep['id']}_q{n}.mp3", force=True)
            except Exception as exc:
                print(f"[Prep] Không tạo lại audio q{n}: {exc}")
    if changed_questions:
        background.add_task(regenerate_audio)
    log_application_event(app_id, app["email"], "questions_edited", "HR đã chỉnh sửa nội dung câu hỏi trước khi gửi link.", {"question_count": len(cleaned), "audio_regenerated_count": len(changed_questions)})
    with db() as conn:
        saved = conn.execute("SELECT * FROM interview_prep WHERE id=?", (prep["id"],)).fetchone()
    result = _prep_from_row(saved)
    return {"ok": True, "prep_id": result["prep_id"], "questions": [{"n": n, **q} for n, q in result["questions"].items()]}




@router.post("/admin/applications/{app_id}/reject")
def admin_reject_application(app_id: str, x_admin_key: str = Header(None)):
    """§ Feature (6): HR từ chối CV → cập nhật status=failed → gửi Email Fail."""
    require_admin(x_admin_key)
    from backend.services.email_service import send_fail_email
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")

        conn.execute(
            "UPDATE cv_applications SET status='failed' WHERE id=?", (app_id,)
        )

    # Gửi email Fail
    send_fail_email(row["name"], row["email"], row["job_id"], app_id)
    log_application_event(
        app_id,
        row["email"],
        "application_rejected",
        "Chúng tôi đã gửi email thông báo kết quả xét duyệt hồ sơ tới hộp thư của bạn — vui lòng kiểm tra email để xem chi tiết.",
        {"job_id": row["job_id"]},
    )
    print(f"[HR Reject] {app_id} → failed → Email sent to {row['email']}")
    return {"ok": True, "app_id": app_id, "status": "failed", "msg": f"Đã từ chối và gửi email kết quả tới {row['email']}"}


@router.get("/admin/stats")
def admin_stats(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                                      AS total,
                SUM(CASE WHEN status='passed'  THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status LIKE 'pending_hr_approval%' THEN 1 ELSE 0 END) AS pending_approval,
                ROUND(AVG(CASE
                    WHEN cv_score IS NOT NULL AND cv_score > 5 THEN cv_score / 2.0
                    WHEN cv_score IS NOT NULL THEN cv_score
                    ELSE NULL
                END), 2) AS avg_score,
                (SELECT COUNT(*) FROM interviews WHERE status IN ('submitted', 'pending_review')) AS submitted_interviews,
                (SELECT COUNT(*) FROM interviews WHERE status='evaluated') AS evaluated_interviews,
                (SELECT COUNT(*) FROM cv_applications WHERE status='pending'
                    AND COALESCE(application_source,'') != 'api'
                    AND LOWER(COALESCE(job_id,'')) NOT GLOB 'jd_*') AS new_applications
            FROM cv_applications WHERE COALESCE(application_source,'') != 'api'
              AND LOWER(COALESCE(job_id,'')) NOT GLOB 'jd_*'
        """).fetchone()
    return dict(row)


# ─────────────────────────────────────────────────────────────
# § Feature (7): Evaluation API — Phiếu Đánh Giá 3 Vòng
# ─────────────────────────────────────────────────────────────

@router.post("/admin/applications/{app_id}/evaluation")
async def save_evaluation(app_id: str, request: Request, x_admin_key: str = Header(None)):
    """Lưu hoặc cập nhật phiếu đánh giá 1 vòng cho ứng viên.
    Body JSON: { round: 1|2|3, evaluator: str, data: {...}, decision: 'pass'|'fail'|'pending' }
    """
    require_admin(x_admin_key)
    body = await request.json()
    round_num  = body.get("round")
    evaluator  = body.get("evaluator", "HR")
    data_json  = json.dumps(body.get("data", {}), ensure_ascii=False)
    decision   = body.get("decision", "pending")
    now        = time.strftime("%Y-%m-%dT%H:%M:%S")

    if round_num not in (1, 2, 3):
        raise HTTPException(400, "round phải là 1, 2 hoặc 3")

    # Calculate score on 10-scale
    criteria = body.get("data", {}).get("criteria", [])
    total_score = sum(c.get("score", 0) for c in criteria)
    if round_num == 1:
        max_score = len(criteria) * 1 if criteria else 1
    elif round_num == 2:
        max_score = len(criteria) * 5 if criteria else 1
    else:
        max_score = len(criteria) * 5 if criteria else 1
    
    scaled_score = round((total_score / max_score) * 10.0, 1) if criteria else None
    summary_note = body.get("data", {}).get("summary", "")

    status_col = f"eval_round{round_num}_status"
    with db() as conn:
        # Upsert evaluation
        conn.execute("""
            INSERT INTO evaluations (app_id, round, evaluator, data, decision, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id, round) DO UPDATE SET
                evaluator  = excluded.evaluator,
                data       = excluded.data,
                decision   = excluded.decision,
                updated_at = excluded.updated_at
        """, (app_id, round_num, evaluator, data_json, decision, now, now))
        # Cập nhật trạng thái vào cv_applications
        conn.execute(
            f"UPDATE cv_applications SET {status_col}=? WHERE id=?",
            (decision, app_id)
        )
        # Đồng bộ sang bảng interviews (Kết quả xét duyệt)
        if round_num == 1:
            conn.execute(
                "UPDATE interviews SET hr_score=?, hr_notes=? WHERE cv_path LIKE ?",
                (scaled_score, summary_note, f"%{app_id}.pdf")
            )
        elif round_num == 2:
            conn.execute(
                "UPDATE interviews SET expert_score=?, expert_notes=? WHERE cv_path LIKE ?",
                (scaled_score, summary_note, f"%{app_id}.pdf")
            )
        app_row = conn.execute("SELECT email FROM cv_applications WHERE id=?", (app_id,)).fetchone()

    if app_row:
        log_application_event(
            app_id,
            app_row["email"],
            "evaluation_saved",
            f"Đã lưu phiếu đánh giá vòng {round_num}: {decision}.",
            {"round": round_num, "decision": decision, "score": scaled_score, "evaluator": evaluator},
        )

    return {"ok": True, "app_id": app_id, "round": round_num, "decision": decision}


@router.get("/admin/applications/{app_id}/evaluation")
def get_evaluations(app_id: str, x_admin_key: str = Header(None)):
    """Lấy toàn bộ phiếu đánh giá 3 vòng của một ứng viên."""
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM evaluations WHERE app_id=? ORDER BY round", (app_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            pass
        result.append(d)
    return {"app_id": app_id, "evaluations": result}



@router.get("/admin/feedback/stats")
def feedback_stats(x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        rows = conn.execute(
            "SELECT position_id, ratings, nps FROM candidate_feedback ORDER BY created_at DESC"
        ).fetchall()

    stats = {}
    for r in rows:
        pos = r["position_id"] or "unknown"
        if pos not in stats:
            stats[pos] = {"count": 0, "nps_sum": 0, "nps_count": 0, "ratings_sum": {}}
        stats[pos]["count"] += 1
        if r["nps"] is not None:
            stats[pos]["nps_sum"]   += r["nps"]
            stats[pos]["nps_count"] += 1
        try:
            for k, v in json.loads(r["ratings"] or "{}").items():
                stats[pos]["ratings_sum"].setdefault(k, []).append(float(v))
        except Exception:
            pass

    result = []
    for pos, s in stats.items():
        avg_ratings = {k: round(sum(v)/len(v), 2) for k, v in s["ratings_sum"].items()}
        result.append({
            "position_id": pos,
            "count":       s["count"],
            "avg_nps":     round(s["nps_sum"] / s["nps_count"], 1) if s["nps_count"] else None,
            "avg_ratings": avg_ratings,
        })
    return {"total_responses": len(rows), "by_position": result}


@router.post("/interview/{interview_id}/request-reinterview")
async def request_reinterview(interview_id: str, body: dict,
                              x_admin_key: str = Header(None)):
    """
    §21 — Phỏng vấn lại: KHÔNG tạo interview mới.
    Tạo prep mới (linked cùng app_ref) → cập nhật interview gốc status='pending_reinterview'
    → gửi email với link có ?reiv={interview_id} để submit ghi đè vào interview gốc.
    body: { "reason": "...", "scope": "07,08" }
    """
    require_admin(x_admin_key)
    scope  = body.get("scope", "07,08")
    reason = body.get("reason", "")
    now    = time.strftime("%Y-%m-%dT%H:%M:%S")

    with db() as conn:
        iv = conn.execute(
            "SELECT i.*, c.name, c.email FROM interviews i LEFT JOIN candidates c ON i.candidate_id=c.id WHERE i.id=?",
            (interview_id,)
        ).fetchone()
        if not iv:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")

        # Lấy app_ref + nội dung câu hỏi trong phạm vi (scope) từ prep cũ, để
        # prep mới cũng linked cùng app_ref và mang đúng câu hỏi cần hỏi lại.
        from backend.services.prep_service import _prep_from_row, normalize_interview_config
        app_ref = None
        scoped_questions = {}
        if iv["prep_id"]:
            old_prep = conn.execute("SELECT * FROM interview_prep WHERE id=?", (iv["prep_id"],)).fetchone()
            if old_prep:
                app_ref = old_prep["app_ref"]
                resolved = _prep_from_row(old_prep)
                wanted = {s.strip() for s in scope.split(",") if s.strip()}
                scoped_questions = {n: q for n, q in resolved["questions"].items() if n in wanted}

        # Tạo prep mới linked cùng app_ref → POST /interview/prep sẽ dùng prep này (ORDER BY created_at DESC)
        new_prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()
        new_frozen = {
            "prep_id": new_prep_id,
            "intro_audio": f"/audio/intro_{iv['position_id']}.mp3",
            "questions": scoped_questions,
            "follow_up_limit": normalize_interview_config(None)["PART_3_FOLLOW_UP"],
        }
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, scope, created_at, questions_json) VALUES (?,?,?,?,?,?,?,?)",
            (new_prep_id, app_ref, iv["position_id"], "", "", scope, now, json.dumps(new_frozen, ensure_ascii=False)),
        )

        # Cập nhật interview GỐC: đánh dấu pending_reinterview, lưu scope
        conn.execute(
            "UPDATE interviews SET status='pending_reinterview', reinterview_scope=?, prep_id=? WHERE id=?",
            (scope, new_prep_id, interview_id),
        )

    # Email với link chứa reiv= để submit biết ghi vào interview gốc
    candidate_email = iv["email"]  # may be NULL for old candidates
    candidate_name  = iv["name"] or "Ứng viên"
    app_row = None
    if not candidate_email and app_ref:
        # Fallback: look up email from cv_applications via app_ref
        with db() as conn:
            _app = conn.execute(
                "SELECT id, email, level, name FROM cv_applications WHERE id=?", (app_ref,)
            ).fetchone()
            if _app:
                candidate_email = _app["email"]
                app_row = _app
                if not iv["name"]:
                    candidate_name = _app["name"] or "Ứng viên"
    if candidate_email:
        if app_row is None:
            with db() as conn:
                app_row = conn.execute(
                    "SELECT id, level FROM cv_applications WHERE email=? ORDER BY applied_at DESC LIMIT 1",
                    (candidate_email,)
                ).fetchone()
        ref = app_ref if app_ref else (app_row["id"] if app_row else "")
        lv  = app_row["level"] if app_row else (iv["level"] or "Junior")
        base_pos = iv["position_id"]
        for _lv in _JOB_LEVELS:
            if base_pos.startswith(_lv + "_"):
                base_pos = base_pos[len(_lv)+1:]
                break
        iv_link = f"{INTERVIEW_URL}?ref={ref}&pos={base_pos}&lv={lv}&reiv={interview_id}&scope={scope}"
        send_reinterview_email(candidate_name, candidate_email, iv["position_id"], iv_link, reason, scope)

    return {"ok": True, "interview_id": interview_id, "scope": scope}


@router.get("/admin/applications/{app_id}/prev-interview")
def get_prev_interview(app_id: str, x_admin_key: str = Header(None)):
    """§20 — Lấy interview cũ nhất của ứng viên cùng email để so sánh."""
    require_admin(x_admin_key)
    with db() as conn:
        app = conn.execute("SELECT email, job_id, prev_app_id FROM cv_applications WHERE id=?", (app_id,)).fetchone()
        if not app:
            raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
        if not app["prev_app_id"]:
            return {"has_prev": False}
        prev_apps = conn.execute(
            "SELECT id FROM cv_applications WHERE id=?", (app["prev_app_id"],)
        ).fetchone()
        if not prev_apps:
            return {"has_prev": False}
        prev_ivs = conn.execute("""
            SELECT i.id, i.status, i.submitted_at,
                   (
                     SELECT ROUND(AVG(group_score), 1)
                     FROM (
                       SELECT AVG(CASE ax.ai_level
                         WHEN 'nắm vững' THEN 10.0 WHEN 'am hiểu' THEN 7.5
                         WHEN 'có biết qua' THEN 5.0 WHEN 'không biết' THEN 0.0
                         ELSE NULL END) AS group_score
                       FROM answers ax
                       WHERE ax.interview_id = i.id
                       GROUP BY ax.attempt_number,
                         CASE
                           WHEN instr(ax.question_number, '.') > 0 THEN substr(ax.question_number, 1, instr(ax.question_number, '.') - 1)
                           ELSE ax.question_number
                         END
                     )
                   ) as avg_score
            FROM interviews i
            LEFT JOIN answers a ON a.interview_id = i.id
            LEFT JOIN candidates c ON i.candidate_id = c.id
            WHERE c.email = ? AND i.id != (
                SELECT id FROM interviews WHERE candidate_id = (
                    SELECT id FROM candidates WHERE email = ? LIMIT 1
                ) ORDER BY submitted_at DESC LIMIT 1
            )
            GROUP BY i.id ORDER BY i.submitted_at DESC LIMIT 1
        """, (app["email"], app["email"])).fetchone()
        return {"has_prev": bool(prev_ivs), "prev_interview": dict(prev_ivs) if prev_ivs else None}
