# PAI HR - ATS Phỏng Vấn AI

Ứng dụng ATS/phỏng vấn trực tuyến dùng FastAPI + frontend HTML/JS. Hệ thống hỗ trợ nộp CV, chấm CV bằng AI, gửi câu hỏi làm rõ, đặt lịch phỏng vấn, phỏng vấn voice, follow-up question, chấm điểm sau phỏng vấn và tích hợp proctoring camera CTPAI.

## Thành Phần

- `backend/`: FastAPI API, SQLite schema, router và service AI/email/proctoring.
- `frontend/`: các màn hình `apply`, `admin`, `interview`, `candidate/reply`.
- `outputs/`: dữ liệu runtime như CV upload, audio phỏng vấn, audio câu hỏi.
- `security/`: báo cáo scan bảo mật, remediation plan và test cases.

## Yêu Cầu

- Python 3.11 khuyến nghị.
- `ffmpeg` và công cụ đọc PDF/DOCX nếu chạy đầy đủ STT/extract CV.
- API keys:
  - `OPENAI_API_KEY`
  - `ELEVENLABS_API_KEY`
  - `ADMIN_KEY`
  - `API_TOKEN` cho external API v1, không dùng chung với `ADMIN_KEY`.

## Cài Đặt

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Sau đó sửa `.env`.

Ví dụ cấu hình tối thiểu:

```env
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
ADMIN_KEY=change-me-to-a-long-random-admin-secret
API_TOKEN=change-me-to-a-long-random-api-token
TEMP_FILE_SECRET=change-me-to-a-long-random-temp-file-secret

PORT=8001
INTERVIEW_URL=http://localhost:8001/interview
ALLOWED_ORIGINS=http://localhost:8001,http://127.0.0.1:8001
```

## Proctoring / Ngrok

Khi dùng CTPAI qua ngrok, `.env` cần dạng:

```env
PROCTORING_API_URL=https://service.ctpai.vn/detection/rule-engine/api/v1
PROCTORING_API_KEY=...
PROCTORING_EMBED_PUBLIC_BASE=https://service.ctpai.vn/detection/
PROCTORING_WEBHOOK_SECRET=change-me-to-a-long-random-webhook-secret
PROCTORING_WEBHOOK_REQUIRE_SECRET=true
PUBLIC_WEBHOOK_DOMAIN=https://your-ngrok-domain.ngrok-free.dev
```

Ngrok phải trỏ đúng port app đang chạy. Nếu chạy app ở `8001`:

```bash
ngrok http 8001
```

Lỗi `ERR_NGROK_8012` nghĩa là ngrok tới được agent nhưng không thấy service local ở port đó. Kiểm tra bằng:

```bash
curl http://127.0.0.1:8001/health
```

## Chạy App

Dev/local port `8001`:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

Nếu muốn dùng port mặc định theo code/env `8080`:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Các URL chính:

- Candidate apply: `http://localhost:8001/apply`
- Admin: `http://localhost:8001/admin`
- Interview: `http://localhost:8001/interview`
- Candidate reply: `http://localhost:8001/candidate/reply?ref=APP-...`
- Health check: `http://localhost:8001/health`

## Flow Chính

1. Ứng viên nộp CV ở `/apply`.
2. Backend lưu CV, extract text, gọi AI chấm điểm và sinh câu hỏi làm rõ.
3. Admin xem hồ sơ ở `/admin`, duyệt/gửi email câu hỏi hoặc link phỏng vấn.
4. Ứng viên trả lời câu hỏi làm rõ ở `/candidate/reply`.
5. Admin đặt lịch phỏng vấn; link interview có slot time.
6. Trang interview xin quyền mic/cam trước, sau đó bật fullscreen/anti-cheat.
7. Proctoring stream camera về CTPAI, webhook log cảnh báo về app.
8. Sau khi nộp bài, backend chấm transcript/audio và admin xem report.

## External API v1

Tất cả endpoint `/api/v1/*` cần:

```http
Authorization: Bearer <API_TOKEN>
```

Ví dụ:

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  http://localhost:8001/api/v1/report/APP-XXXXXXXX
```

Lưu ý: `API_TOKEN` không fallback sang `ADMIN_KEY`.

## Bảo Mật Đã Có

- Admin API kiểm tra `X-Admin-Key` ở backend.
- External API v1 dùng token riêng `API_TOKEN`.
- Proctoring alerts cần token ký, không đọc bằng mỗi `app_id`.
- Webhook deep-analysis chặn SSRF: chỉ HTTPS, block localhost/private/link-local/reserved IP, không follow redirect.
- Security headers/CSP/Permissions-Policy được set ở FastAPI middleware.
- File tạm `/temp_pushbacks/*` cần HMAC token.
- Upload CV/audio có giới hạn extension và size.
- Admin key phía frontend dùng `sessionStorage`; bản cũ trong `localStorage` sẽ được migrate/xóa khi mở app.

## Smoke Test Nhanh

```bash
.venv/bin/python -m py_compile backend/main.py backend/routers/*.py backend/services/*.py

node -e "const fs=require('fs'); for (const f of ['frontend/interview.html','frontend/admin.html','frontend/apply.html','frontend/candidate_reply.html']) { const s=fs.readFileSync(f,'utf8'); const js=[...s.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)].map(m=>m[1]).join('\\n'); new Function(js); console.log(f, 'ok'); }"

curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/jobs
curl -i http://127.0.0.1:8001/admin/stats
```

Kỳ vọng:

- `/health` trả `200`.
- `/jobs` trả `200`.
- `/admin/stats` thiếu key trả `401`.

## Database

- SQLite file: `ats_phongvan.db`.
- App tự tạo/migrate bảng khi startup.
- Không commit DB, log, `.env`, file key hoặc dữ liệu trong `outputs/`.

Reset local DB:

```bash
rm ats_phongvan.db
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

Chỉ reset khi chắc chắn không cần dữ liệu local.

## Ghi Chú Vận Hành

- Sau khi sửa backend, restart uvicorn.
- Sau khi sửa frontend HTML, refresh tab hoặc mở tab mới để tránh cache/tab cũ.
- Nếu proctoring không có alert, kiểm tra `WS: connected` trên trang interview và webhook domain public.
- Nếu ngrok báo upstream refused, kiểm tra app đang listen đúng port.
