# API Security Review

## Findings

- SEC-001: outbound deep-analysis webhook can SSRF internal/private URLs.
- SEC-003: proctoring alerts are readable by `app_id` only.
- SEC-005: raw AI/STT/LLM output is printed to server logs.
- No app-wide rate limiting or request throttling found.
- Many endpoints return direct exception strings in 4xx/5xx paths; risk of implementation detail disclosure.

## Injection Review

- SQL access mostly uses parameterized SQLite queries.
- Dynamic SQL in schema migration uses static allowlisted column names from code.
- Dynamic `IN (...)` placeholder construction in admin proctoring logs is parameterized for values.
- No shell command construction from user input was found in request handlers; `pdftotext` is invoked with a path created by server-side upload handling.

## Frontend Browser Review

- Multiple pages use `innerHTML` heavily. Some values are escaped, but coverage is inconsistent.
- Admin key is stored in `localStorage`, increasing blast radius of XSS.
- No global CSP/security headers middleware found.
- CORS allowlist defaults to localhost/current public domain; no wildcard credential issue observed.
