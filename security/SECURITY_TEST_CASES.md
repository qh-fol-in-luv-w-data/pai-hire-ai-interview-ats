# Security Test Cases

## Auth And Authorization

| ID | Case | Expected |
|---|---|---|
| AUTH-001 | Call admin API without `X-Admin-Key` | 401 |
| AUTH-002 | Call admin API with wrong key | 401 |
| AUTH-003 | Call `/api/v1/report/{app_id}` with `ADMIN_KEY` after SEC-002 fix | 401 |
| AUTH-004 | Call `/api/v1/report/{app_id}` with valid scoped API token | 200 |
| AUTH-005 | Call proctoring alerts with app id only after SEC-003 fix | 401/403 |
| AUTH-006 | Call proctoring alerts with valid signed token | 200 |

## Slot And Candidate Flow

| ID | Case | Expected |
|---|---|---|
| SLOT-001 | Validate slot before start | 403 not_started |
| SLOT-002 | Validate slot within range | 200 |
| SLOT-003 | Validate slot after end | 403 expired |
| SLOT-004 | Create schedule with end <= start | 422 |
| CAND-001 | Submit candidate reply twice | second request rejected |
| CAND-002 | Brute-force invalid `APP-XXXXXXXX` refs | rate limit/404 without detail |

## Injection And XSS

| ID | Case | Expected |
|---|---|---|
| XSS-001 | Candidate name contains `<img onerror=...>` | rendered escaped |
| XSS-002 | Admin note contains `<script>` | rendered escaped |
| SQLI-001 | `app_id` contains SQL marker | rejected/not found, no SQL error |
| LOG-001 | Input contains CRLF/log marker | logs structured/redacted |

## Upload

| ID | Case | Expected |
|---|---|---|
| UP-001 | `.exe` renamed to `.pdf` | rejected after magic-byte check |
| UP-002 | SVG/HTML upload as CV | rejected |
| UP-003 | Oversized CV > 10 MB | 413 |
| UP-004 | Oversized audio > 25 MB | 413 |
| UP-005 | Malformed PDF parser crash sample | safe 422/500 without stack trace |

## SSRF

| ID | Case | Expected |
|---|---|---|
| SSRF-001 | webhook_url `http://127.0.0.1:8001/health` | rejected |
| SSRF-002 | webhook_url `http://localhost` | rejected |
| SSRF-003 | webhook_url `http://169.254.169.254/latest/meta-data` | rejected |
| SSRF-004 | public URL redirecting to private IP | rejected after redirect/DNS validation |
| SSRF-005 | allowlisted HTTPS webhook | accepted |

## Headers And Browser

| ID | Case | Expected |
|---|---|---|
| HDR-001 | GET `/admin` | CSP, X-Content-Type-Options, Referrer-Policy present |
| HDR-002 | GET `/interview` | Permissions-Policy limits camera/mic to self |
| CORS-001 | Origin from unknown domain | no CORS allow |
| STORAGE-001 | Login admin after session fix | no admin secret in localStorage |

## Runtime Manual

| ID | Case | Expected |
|---|---|---|
| RUNTIME-001 | Request `/.env`, `/.git/config`, `/ngrok.log` via public domain | 404 |
| RUNTIME-002 | Proctoring webhook missing secret | 401 |
| RUNTIME-003 | Submit interview and inspect logs | no raw transcript/PII |
