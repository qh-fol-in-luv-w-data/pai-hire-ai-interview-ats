from fastapi import FastAPI, Request, Header
from backend.patch_asgi import PathRewriteMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.config import ALLOWED_ORIGINS, BASE_DIR, FRONTEND_DIR, QUESTION_AUDIO_DIR, TEMP_PUSHBACKS_DIR
from backend.services.auth_service import current_user
from backend.services.rate_limit import enforce
from backend.routers import admin, feedback, interview, jobs, webhook, evaluate, candidate, api_v1, proctoring, auth, companies, payments
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
    path = request.url.path
    if request.method == "POST" and path in {"/auth/login", "/auth/register", "/auth/check-user", "/api/enterprise/register"}:
        enforce(request, "identity", 12, 60)
    elif request.method == "POST" and path.startswith("/api/v1/"):
        enforce(request, "external-api", 30, 60)
    elif request.method == "POST" and path.startswith("/interview/"):
        enforce(request, "interview", 40, 60)
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

UI_DIR = FRONTEND_DIR / "dist" if (FRONTEND_DIR / "dist").is_dir() else FRONTEND_DIR

app.mount("/audio", StaticFiles(directory=str(QUESTION_AUDIO_DIR)), name="audio")
app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")
if (UI_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(UI_DIR / "assets")), name="frontend-assets")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(companies.router)
app.include_router(companies.public_router)
app.include_router(companies.legacy_public_router)
app.include_router(payments.router)
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
        (UI_DIR / filename).read_text(encoding="utf-8"),
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

@app.get("/code.html", include_in_schema=False)
def code_page():
    return FileResponse(UI_DIR / "code.html", headers={"Cache-Control": "no-store"})

@app.get("/report_print.html", include_in_schema=False)
def report_print_page():
    return FileResponse(UI_DIR / "report_print.html", headers={"Cache-Control": "no-store"})

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


@app.get("/outputs/{file_path:path}")
def protected_output(file_path: str, request: Request, authorization: str | None = Header(None)):
    """Serve CV/audio/video only to the owning candidate or an admin session."""
    root = (BASE_DIR / "outputs").resolve()
    path = (root / file_path).resolve()
    if root not in path.parents or not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(404, "Không tìm thấy tệp")
    actor = current_user(request, authorization)
    if actor.get("role") not in {"admin", "platform_admin"}:
        relative = str(path.relative_to(BASE_DIR))
        with __import__("backend.database", fromlist=["db"]).db() as conn:
            owner = conn.execute(
                """SELECT ca.email FROM cv_applications ca WHERE ca.cv_path=?
                   UNION SELECT c.email FROM interviews i JOIN candidates c ON c.id=i.candidate_id
                   WHERE i.cv_path=? OR i.video_path=?
                   UNION SELECT c.email FROM answers a JOIN interviews i ON i.id=a.interview_id
                   JOIN candidates c ON c.id=i.candidate_id WHERE a.audio_path=? LIMIT 1""",
                (relative, relative, relative, relative),
            ).fetchone()
        if not owner or (owner["email"] or "").lower() != (actor.get("email") or "").lower():
            from fastapi import HTTPException
            raise HTTPException(403, "Bạn không có quyền truy cập tệp này")
    return FileResponse(path)

@app.get("/", response_class=HTMLResponse)
def root_page():
    return html_page("candidate.html")

@app.get("/interview", response_class=HTMLResponse)
def interview_page():
    return html_page("interview.html")

@app.get("/apply", response_class=HTMLResponse)
def apply_page():
    return html_page("candidate.html")

@app.get("/apply/{job_id}", response_class=HTMLResponse)
def apply_job_page(job_id: str):
    return html_page("candidate.html")

@app.get("/enterprise", response_class=HTMLResponse)
@app.get("/enterprise/{path:path}", response_class=HTMLResponse)
def enterprise_page(path: str = ""):
    return html_page("candidate.html")

@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page():
    return html_page("candidate.html")

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return html_page("admin.html")

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    return html_page("admin.html")

@app.get("/admin/{path:path}", response_class=HTMLResponse)
def admin_nested_page(path: str):
    return html_page("admin.html")

@app.get("/candidate/reply", response_class=HTMLResponse)
def candidate_reply_page():
    return HTMLResponse(
        (UI_DIR / "candidate.html").read_text(encoding="utf-8"),
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
    return html_page("candidate.html")

from fastapi.responses import RedirectResponse
@app.get("/v1/slot/{token}/validate", include_in_schema=False)
def redirect_v1_slot_validate(token: str):
    return RedirectResponse(url=f"/api/v1/slot/{token}/validate", status_code=307)
