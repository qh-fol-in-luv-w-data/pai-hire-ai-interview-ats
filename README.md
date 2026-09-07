# PAI HR - ATS & Phỏng Vấn AI

Nền tảng **ATS multi-tenant** dùng FastAPI + React (TypeScript + Vite). Ứng viên nộp CV → AI chấm điểm → gửi câu hỏi làm rõ → đặt lịch → phỏng vấn voice AI có follow-up → chấm điểm sau phỏng vấn, kèm proctoring camera qua CTPAI.

- Repo: [qh-fol-in-luv-w-data/pai-hire-ai-interview-ats](https://github.com/qh-fol-in-luv-w-data/pai-hire-ai-interview-ats)

## Tính năng chính

- Multi-tenant: mỗi công ty (`companies`) có tài khoản enterprise riêng, quota riêng.
- Chấm CV + sinh câu hỏi làm rõ tự động bằng LLM.
- Phỏng vấn voice (ElevenLabs + edge-tts), follow-up question, chấm điểm transcript.
- Proctoring camera realtime (CTPAI), webhook signed HMAC.
- Nạp quota tự động qua **SePay** webhook.
- External API v1 với Bearer token riêng.

## Yêu cầu

- Python 3.11 khuyến nghị, `ffmpeg`, MinIO (object storage).
- API keys chính: `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `ADMIN_KEY`, `API_TOKEN`, `TEMP_FILE_SECRET`.
- SMTP để gửi email ứng viên, cấu hình `PROCTORING_*` nếu bật CTPAI, `SEPAY_*` nếu bật thanh toán.
- Node.js 18+ cho frontend.

## Cài đặt

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # điền các key ở trên
```

Chạy dev (port 8001):

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

Frontend:

```bash
cd frontend
npm install
npm run dev              # dev — hoặc: npm run build
npm run test             # Vitest
npm run test:e2e         # Playwright
```

Docker: `docker-compose up -d` (deploy: `deploy.sh` / `deploy-dev.sh`). CI/CD tự deploy qua SSH khi push `main` (`.github/workflows/deploy.yml`).

## URL chính

- `/apply`, `/candidate/reply?ref=APP-...` — luồng ứng viên
- `/admin` — trang quản trị (Enterprise auth)
- `/interview` — phỏng vấn voice
- `/api/v1/*` — external API (Bearer `API_TOKEN`)
- `/api/webhooks/sepay` — nạp quota tự động
- `/health` — health check

## Bảo mật đã có

- Admin API: `X-Admin-Key`; enterprise API: session token.
- External API v1 dùng token riêng, **không** fallback sang `ADMIN_KEY`.
- Webhook (proctoring / SePay) verify HMAC + chặn SSRF.
- Upload CV / audio giới hạn extension + size.
- Security headers / CSP / Permissions-Policy set sẵn ở middleware.
- File tạm `/temp_pushbacks/*` ký bằng HMAC.

## Database

- SQLite `ats_phongvan.db`, tự tạo/migrate lúc startup.
- File runtime (CV, audio) lưu ở `outputs/` hoặc MinIO — **không commit**.

Reset local DB:

```bash
rm ats_phongvan.db && .venv/bin/uvicorn backend.main:app --port 8001
```
