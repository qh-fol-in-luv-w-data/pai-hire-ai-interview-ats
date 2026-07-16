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
from backend.config import ADMIN_KEY, require_admin, PASS_SCORE, OUTPUT_DIR, CV_UPLOAD_DIR, TEMP_PUSHBACKS_DIR, _find_position_files, _parse_q0306, QUESTIONS_BANK, CATEGORY_LABELS

router = APIRouter()

@router.post("/interview/incident")
async def log_incident(body: dict):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        conn.execute(
            "INSERT INTO incidents (interview_id, type, description, created_at) VALUES (?,?,?,?)",
            (body.get("interview_id"), body.get("type", "unknown"),
             body.get("description", ""), now),
        )
    return {"ok": True}


@router.post("/feedback")
async def submit_feedback(body: dict):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db() as conn:
        conn.execute(
            "INSERT INTO candidate_feedback (position_id, ratings, nps, comments, created_at) VALUES (?,?,?,?,?)",
            (
                body.get("position_id"),
                json.dumps(body.get("ratings", {}), ensure_ascii=False),
                body.get("nps"),
                body.get("comments", ""),
                now,
            ),
        )
    return {"ok": True}


