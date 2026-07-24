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
from backend.database import db
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS
from backend.security import bounded_text

router = APIRouter()

@router.post("/interview/incident")
async def log_incident(body: dict):
    interview_id = bounded_text(body.get("interview_id") or "", "interview_id", 64)
    app_ref = bounded_text(body.get("app_ref") or "", "app_ref", 64)
    incident_type = bounded_text(body.get("type", "unknown"), "type", 64)
    description = bounded_text(body.get("description", ""), "description", 1000)
    if not interview_id:
        if re.fullmatch(r"APP-[A-F0-9]{8}", app_ref or ""):
            interview_id = app_ref
        else:
            raise HTTPException(400, "Thiếu interview_id")
    if interview_id.startswith("IV-"):
        with db() as conn:
            exists = conn.execute("SELECT 1 FROM interviews WHERE id=?", (interview_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Không tìm thấy interview")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        conn.execute(
            "INSERT INTO incidents (interview_id, type, description, created_at) VALUES (?,?,?,?)",
            (interview_id, incident_type, description, now),
        )
    return {"ok": True}


@router.post("/feedback")
async def submit_feedback(body: dict):
    comments = bounded_text(body.get("comments", ""), "comments", 2000)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        conn.execute(
            "INSERT INTO candidate_feedback (position_id, ratings, nps, comments, created_at) VALUES (?,?,?,?,?)",
            (
                body.get("position_id"),
                json.dumps(body.get("ratings", {}), ensure_ascii=False),
                body.get("nps"),
                comments,
                now,
            ),
        )
    return {"ok": True}
