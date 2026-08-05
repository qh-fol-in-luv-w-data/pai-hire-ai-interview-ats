from fastapi import FastAPI
from backend.patch_asgi import PathRewriteMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.config import ALLOWED_ORIGINS, BASE_DIR, FRONTEND_DIR, QUESTION_AUDIO_DIR, TEMP_PUSHBACKS_DIR
from backend.routers import admin, feedback, interview, jobs, webhook, evaluate, candidate, api_v1, proctoring, auth
from backend.security import verify_temp_file_token

app = FastAPI(title="ATS Phỏng Vấn API", version="2.0.0")
app.add_middleware(PathRewriteMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def rewrite_api_path(request, call_next):
    if request.url.path.startswith("/v1/"):
        request.scope["path"] = "/api" + request.scope["path"]
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        'camera=(self "https://service.ctpai.vn"), microphone=(self "https://service.ctpai.vn"), geolocation=(), payment=(), usb=()',
    )
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self' https://service.ctpai.vn wss://service.ctpai.vn; "
        "frame-src 'self' https://service.ctpai.vn; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "object-src 'none'",
    )
    return response

app.mount("/audio", StaticFiles(directory=str(QUESTION_AUDIO_DIR)), name="audio")
app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR)), name="ui")
app.mount("/outputs", StaticFiles(directory=str(BASE_DIR / "outputs")), name="outputs")

app.include_router(auth.router)
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


def html_page(filename: str) -> HTMLResponse:
    return HTMLResponse(
        (FRONTEND_DIR / filename).read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )

@app.on_event("startup")
def startup():
    init_db()
    


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

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

@app.get("/", response_class=HTMLResponse)
def root_page():
    return html_page("apply.html")

@app.get("/interview", response_class=HTMLResponse)
def interview_page():
    return HTMLResponse(
        (FRONTEND_DIR / "interview.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )

@app.get("/apply", response_class=HTMLResponse)
def apply_page():
    return html_page("apply.html")

@app.get("/apply/{job_id}", response_class=HTMLResponse)
def apply_job_page(job_id: str):
    return html_page("apply.html")

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return html_page("admin.html")

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    return html_page("admin.html")

@app.get("/candidate/reply", response_class=HTMLResponse)
def candidate_reply_page():
    return HTMLResponse(
        (FRONTEND_DIR / "candidate_reply.html").read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Robots-Tag": "noindex, noarchive, nosnippet",
        },
    )

@app.get("/history", response_class=HTMLResponse)
@app.get("/candidate/history", response_class=HTMLResponse)
def candidate_history_page():
    return html_page("history.html")

from fastapi.responses import RedirectResponse
@app.get("/v1/slot/{token}/validate", include_in_schema=False)
def redirect_v1_slot_validate(token: str):
    return RedirectResponse(url=f"/api/v1/slot/{token}/validate", status_code=307)
