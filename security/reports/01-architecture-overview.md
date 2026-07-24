# Architecture Overview

- Backend: FastAPI, SQLite, file-system storage under `outputs/`, AI integrations through OpenAI and ElevenLabs, CTPAI proctoring integration.
- Frontend: static HTML/JS served by FastAPI (`/admin`, `/apply`, `/interview`, `/candidate/reply`) plus static `/ui`.
- Auth:
  - Admin endpoints use `X-Admin-Key` compared to `ADMIN_KEY`.
  - External API v1 uses bearer token from DB setting `api_token`, `API_TOKEN`, or fallback `ADMIN_KEY`.
  - Candidate slot validation is public by design and keyed by random slot token.
- Database: SQLite via `backend/database.py`; app initializes schema on startup.
- File handling:
  - CV upload: public apply and authenticated API v1, restricted to PDF/DOCX by extension/content-type mapping and size.
  - Audio upload: interview answer upload, restricted to audio extensions and size.
  - Temporary pushback audio is protected with an HMAC query token.
- Third-party services: OpenAI, ElevenLabs STT/TTS, SMTP, CTPAI proctoring, optional outbound deep-analysis webhook.
- Runtime entry points: public jobs/apply/candidate reply/interview pages, admin dashboard, external `/api/v1/*`, proctoring webhook, deep-analysis webhook.

## Notes

- No `.github` CI workflow directory exists in this working copy.
- Local untracked sensitive-looking files exist (`.env`, `key.pem`, `backend/pai_database.sqlite`, `ngrok.log`) and were not included in the previous commit.
