from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.config import ALLOWED_ORIGINS, BASE_DIR, FRONTEND_DIR, QUESTION_AUDIO_DIR, TEMP_PUSHBACKS_DIR
from backend.routers import admin, feedback, interview, jobs, webhook, evaluate, candidate, api_v1, proctoring
from backend.security import verify_temp_file_token

app = FastAPI(title="ATS Phỏng Vấn API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/audio", StaticFiles(directory=str(QUESTION_AUDIO_DIR)), name="audio")
app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR)), name="ui")

app.include_router(admin.router)
app.include_router(feedback.router)
app.include_router(interview.router)
app.include_router(jobs.router)
app.include_router(webhook.router)
app.include_router(evaluate.router)
app.include_router(candidate.router)
app.include_router(api_v1.router)
app.include_router(proctoring.router)

import asyncio

@app.on_event("startup")
def startup():
    init_db()
    


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/temp_pushbacks/{filename}")
def temp_pushback_audio(filename: str, token: str = None):
    verify_temp_file_token(filename, token)
    if "/" in filename or "\\" in filename or filename.startswith("."):
        from fastapi import HTTPException
        raise HTTPException(400, "Tên file không hợp lệ")
    path = TEMP_PUSHBACKS_DIR / filename
    if not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(404, "Không tìm thấy file")
    return FileResponse(
        path,
        media_type="audio/mpeg" if path.suffix.lower() == ".mp3" else "application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )

@app.get("/interview", response_class=HTMLResponse)
def interview_page():
    return (FRONTEND_DIR / "interview.html").read_text(encoding="utf-8")

@app.get("/apply", response_class=HTMLResponse)
def apply_page():
    return (FRONTEND_DIR / "apply.html").read_text(encoding="utf-8")

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return (FRONTEND_DIR / "admin.html").read_text(encoding="utf-8")

@app.get("/candidate/reply", response_class=HTMLResponse)
def candidate_reply_page():
    return (FRONTEND_DIR / "candidate_reply.html").read_text(encoding="utf-8")
