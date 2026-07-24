# Secret Scan

## Findings

- `.env` exists locally and should stay untracked. Values were not printed in this report.
- `key.pem` exists at repository root locally. Treat as sensitive until confirmed unused/test-only.
- `backend/pai_database.sqlite` and `ngrok.log` exist locally and may contain private applicant/proctoring/session data.
- `.env.example` and README contain placeholder values only, not real secrets.
- Code loads sensitive values from env: `ADMIN_KEY`, `API_TOKEN`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `SMTP_PASS`, `PROCTORING_API_KEY`, `PROCTORING_WEBHOOK_SECRET`, `TEMP_FILE_SECRET`.

## Git Hygiene

- The latest pushed commit did not include `.env`, `key.pem`, sqlite DB, or ngrok log.
- Recommended: ensure `.gitignore` explicitly covers `.env*` except `.env.example`, `*.pem`, `*.key`, `*.sqlite`, `*.db`, `*.log`, and `outputs/`.

## Manual Follow-Up

- Run a historical secret scanner such as `gitleaks detect --redact` before production release.
- Rotate any key that was ever shared through chat, logs, screenshots, or committed history.
