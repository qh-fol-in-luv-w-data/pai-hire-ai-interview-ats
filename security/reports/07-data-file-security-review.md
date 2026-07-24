# Data And File Security Review

## Upload

- CV uploads are limited to `.pdf` and `.docx`, max 10 MB.
- Audio uploads are limited to common audio/webm extensions, max 25 MB.
- Server-generated file names are used for CV/audio in main flows.

## Remaining Gaps

- File validation relies on extension and content-type mapping; no magic-byte verification.
- No malware scan, macro detection, polyglot detection, or PDF active-content stripping.
- Uploaded files are stored on local disk; retention/encryption policy was not found.
- Candidate/application data and transcripts are stored in SQLite without field-level encryption.

## Download

- Temporary generated audio is protected by an HMAC token.
- `/audio` static mount exposes generated question audio; this appears intended and low sensitivity.
- Admin report/data download endpoints require admin key.

## SSRF

- Confirmed SSRF risk exists in `backend/routers/webhook.py` for caller-controlled `webhook_url`.
