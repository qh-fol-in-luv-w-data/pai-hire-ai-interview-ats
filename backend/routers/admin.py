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
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTION_META, CATEGORY_LABELS, _JOB_LEVELS, INTERVIEW_URL

from backend.services.email_service import send_interview_result, send_reinterview_email
router = APIRouter()

@router.get("/admin/interviews")
def admin_list_interviews(
    status: str = None,
    position_id: str = None,
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

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(f"""
            SELECT i.id, i.candidate_id, i.position_id, i.status, i.submitted_at,
                   i.level, i.is_reapplicant, i.reinterview_of, i.cv_path,
                   CASE WHEN i.hod_questions IS NOT NULL AND i.hod_questions != '' THEN 1 ELSE 0 END as has_hod_questions,
                   c.name as candidate_name, c.email as candidate_email,
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
            LIMIT ? OFFSET ?
        """, (*params, limit, offset)).fetchall()

    return {"total": len(rows), "interviews": [dict(r) for r in rows]}


@router.patch("/interview/{interview_id}/review")
async def review_interview(interview_id: str, body: dict):
    """
    body: {
      "status": "reviewed" | "passed" | "failed",
      "answers": { "01": { "score": 8, "notes": "..." }, ... }
    }
    §27 — Khi status=passed/failed → tự động gửi email kết quả cho ứng viên.
    """
    new_status = body.get("status", "reviewed")
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
    where, params = [], []
    if status:
        where.append("status = ?");  params.append(status)
    if job_id:
        where.append("job_id = ?");  params.append(job_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM cv_applications {clause} ORDER BY applied_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()

    return {"total": len(rows), "applications": [dict(r) for r in rows]}


@router.get("/admin/applications/{app_id}")
def admin_get_application(app_id: str, x_admin_key: str = Header(None)):
    require_admin(x_admin_key)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
    data = dict(row)
    if data.get("score_breakdown"):
        data["score_breakdown"] = json.loads(data["score_breakdown"])
    return data


@router.post("/admin/applications/{app_id}/approve")
def admin_approve_application(app_id: str, x_admin_key: str = Header(None)):
    """§ Feature (6): HR duyệt CV → cập nhật status=passed → gửi Email Pass với link phỏng vấn."""
    require_admin(x_admin_key)
    from backend.services.email_service import send_pass_email
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cv_applications WHERE id = ?", (app_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
        if not row["status"].startswith("pending_hr_approval"):
            raise HTTPException(400, f"Hồ sơ đang ở trạng thái '{row['status']}', không cần duyệt lại")

        level = dict(row).get("level", "Junior") or "Junior"
        conn.execute(
            "UPDATE cv_applications SET status='passed' WHERE id=?", (app_id,)
        )

    # Gửi email Pass
    send_pass_email(row["name"], row["email"], row["job_id"], app_id, level=level)
    print(f"[HR Approve] {app_id} → passed → Email sent to {row['email']}")
    return {"ok": True, "app_id": app_id, "status": "passed", "msg": f"Đã duyệt và gửi email mời phỏng vấn tới {row['email']}"}


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
                ROUND(AVG(CASE WHEN cv_score IS NOT NULL THEN cv_score END), 2) AS avg_score
            FROM cv_applications
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

        # Lấy app_ref từ prep cũ (để prep mới cũng linked cùng app_ref)
        app_ref = None
        q05_text = ""
        q06_text = ""
        q07_text = ""
        q08_text = ""
        if iv["prep_id"]:
            old_prep = conn.execute(
                "SELECT app_ref, q05_text, q06_text, q07_text, q08_text FROM interview_prep WHERE id=?",
                (iv["prep_id"],)
            ).fetchone()
            if old_prep:
                app_ref  = old_prep["app_ref"]
                q05_text = old_prep["q05_text"]
                q06_text = old_prep["q06_text"]
                q07_text = old_prep["q07_text"] if "q07_text" in old_prep.keys() else ""
                q08_text = old_prep["q08_text"] if "q08_text" in old_prep.keys() else ""

        # Tạo prep mới linked cùng app_ref → POST /interview/prep sẽ dùng prep này (ORDER BY created_at DESC)
        new_prep_id = "PREP-" + uuid.uuid4().hex[:10].upper()
        conn.execute(
            "INSERT INTO interview_prep (id, app_ref, position_id, q05_text, q06_text, q07_text, q08_text, scope, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_prep_id, app_ref, iv["position_id"], q05_text, q06_text, q07_text, q08_text, scope, now),
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
                   ROUND(AVG(CASE a.ai_level
                     WHEN 'nắm vững' THEN 10.0 WHEN 'am hiểu' THEN 7.5
                     WHEN 'có biết qua' THEN 5.0 WHEN 'không biết' THEN 0.0
                     ELSE NULL END), 1) as avg_score
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


