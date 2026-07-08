from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.config import BASE_DIR, FRONTEND_DIR, QUESTION_AUDIO_DIR, TEMP_PUSHBACKS_DIR
from backend.routers import admin, feedback, interview, jobs, webhook

app = FastAPI(title="ATS Phỏng Vấn API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/audio", StaticFiles(directory=str(QUESTION_AUDIO_DIR)), name="audio")
app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR)), name="ui")
app.mount("/temp_pushbacks", StaticFiles(directory=str(TEMP_PUSHBACKS_DIR)), name="temp_pushbacks")

app.include_router(admin.router)
app.include_router(feedback.router)
app.include_router(interview.router)
app.include_router(jobs.router)
app.include_router(webhook.router)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/interview", response_class=HTMLResponse)
def interview_page():
    return (FRONTEND_DIR / "interview.html").read_text(encoding="utf-8")

@app.get("/apply", response_class=HTMLResponse)
def apply_page():
    return (FRONTEND_DIR / "apply.html").read_text(encoding="utf-8")

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return (FRONTEND_DIR / "admin.html").read_text(encoding="utf-8")
