# Security Scan Report

Date: 2026-07-24  
Scope: `ats_phongvan` source tree, focusing backend, frontend, API, Docker, dependency files, local secret hygiene.  
Mode: Static review plus local syntax/dependency checks. No exploit against production was performed.

## Summary

| Severity | Count |
|---|---:|
| Critical | 0 |
| High | 1 |
| Medium | 5 |
| Low | 2 |

| ID | Finding | Severity | Module | File | Status | Priority |
|---|---|---|---|---|---|---|
| SEC-001 | Outbound webhook allows SSRF to arbitrary HTTP(S) URLs | High | Webhook | `backend/routers/webhook.py` | Fixed | P0 |
| SEC-002 | External API token falls back to admin key | Medium | Auth/API | `backend/routers/api_v1.py` | Fixed | P1 |
| SEC-003 | Proctoring alerts readable by app id without auth | Medium | Proctoring | `backend/routers/proctoring.py` | Fixed | P1 |
| SEC-004 | Admin key stored in localStorage | Medium | Frontend/Auth | `frontend/admin.html`, `frontend/report_print.html`, `frontend/ats_ui.html` | Partially Fixed | P1 |
| SEC-005 | Raw AI/STT output logged to server logs | Medium | Logging/AI | `backend/routers/interview.py` | Fixed | P1 |
| SEC-006 | Missing security headers/CSP middleware | Medium | Backend/Frontend | `backend/main.py` | Fixed | P2 |
| SEC-007 | Upload validation lacks magic-byte/malware checks | Low | Upload | `backend/security.py` | Confirmed | P2 |
| SEC-008 | Docker runs as root and lacks hardening | Low | Container | `Dockerfile`, `docker-compose.yml` | Confirmed | P3 |

## Top Risks

1. SSRF through admin deep-analysis webhook can reach internal services if admin key is compromised or misused.
2. External API and admin API can share the same secret due to fallback behavior.
3. Proctoring events can be read by anyone who knows/guesses a valid application id.
4. Any XSS in admin pages can steal the admin key from localStorage.
5. Raw transcript/LLM output in logs may expose candidate personal data.
6. No rate limiting across public candidate/API endpoints.
7. Weak production hardening due to missing security headers.
8. Upload validation does not inspect magic bytes or scan malicious documents.
9. Python dependencies are unpinned and not audited in this environment.
10. Local secret/data files exist and must remain untracked.

## Findings

### [SEC-001] Outbound Webhook Allows SSRF

- Severity: High
- Status: Fixed
- CWE: CWE-918
- OWASP: API7:2023 Server Side Request Forgery
- File: `backend/routers/webhook.py`
- Lines: 16, 20, 40-41, 70-75
- Function/Endpoint: `POST /api/webhook/generate-deep-analysis`

#### Evidence

`webhook_url` is accepted from the request and only checked for `http`/`https` scheme and `netloc`. The background task then posts to that URL.

#### Root Cause

No allowlist, DNS/IP private-range block, redirect validation, or fixed outbound destination policy.

#### Safe Exploitation Scenario

An actor with admin key can submit a webhook URL pointing to localhost, private network services, or cloud metadata and use the server as a network pivot.

#### Impact

Confidentiality and availability impact against internal services reachable from the server network.

#### Recommendation

Allow only configured webhook domains, or validate resolved IP after DNS and after redirects; block localhost, private, link-local, metadata, `file://`, and non-HTTP(S).

#### Suggested Patch

Add a `validate_webhook_url()` helper with domain allowlist and IP classification before adding the background task.

#### Functional Impact

Integrators must register webhook domains.

#### Verification

Unit test URLs for `127.0.0.1`, `localhost`, `169.254.169.254`, private IP ranges, and private redirects.

### [SEC-002] External API Token Falls Back To Admin Key

- Severity: Medium
- Status: Fixed
- CWE: CWE-287
- OWASP: API2:2023 Broken Authentication
- File: `backend/routers/api_v1.py`
- Lines: 61-72
- Function/Endpoint: `/api/v1/*`

#### Evidence

When DB `api_token` and env `API_TOKEN` are missing, `_get_valid_token()` returns `ADMIN_KEY`.

#### Root Cause

Convenience fallback merges admin and external API trust boundaries.

#### Safe Exploitation Scenario

A third-party integration token accidentally becomes equivalent to admin secret reuse, or admin key leakage grants API v1 report/schedule/score access.

#### Impact

Confidentiality impact for reports and integrity impact for scheduling.

#### Recommendation

Require dedicated `API_TOKEN`; fail closed if not configured. Prefer multiple hashed/scoped API keys.

#### Suggested Patch

Remove `ADMIN_KEY` fallback and store only hashed API tokens with scopes.

#### Functional Impact

Deployments must set `API_TOKEN` or create `api_token` setting.

#### Verification

Unset `API_TOKEN` and DB token; `/api/v1/report/*` must return 500/503 config error, not accept `ADMIN_KEY`.

### [SEC-003] Proctoring Alerts Readable By App ID

- Severity: Medium
- Status: Fixed
- CWE: CWE-639
- OWASP: API1:2023 Broken Object Level Authorization
- File: `backend/routers/proctoring.py`
- Lines: 104-121
- Function/Endpoint: `GET /api/v1/proctoring/alerts`

#### Evidence

Endpoint validates app id format and existence, then returns alert rows without candidate token, slot token, or admin auth.

#### Root Cause

Polling endpoint trusts app id secrecy.

#### Safe Exploitation Scenario

Anyone with a leaked/observed `APP-XXXXXXXX` can read proctoring event types and timestamps.

#### Impact

Candidate privacy exposure and interview integrity metadata leakage.

#### Recommendation

Require a signed session token returned during slot validation or proctoring session creation.

#### Suggested Patch

Add HMAC token bound to app id and expiry; frontend sends it when polling alerts.

#### Functional Impact

Interview frontend needs to persist/send the signed proctoring token.

#### Verification

Calling alerts without token should return 401/403; valid current interview token should work.

### [SEC-004] Admin Key Stored In LocalStorage

- Severity: Medium
- Status: Partially Fixed
- CWE: CWE-922
- OWASP: A05:2021 Security Misconfiguration
- File: `frontend/admin.html`, `frontend/report_print.html`
- Lines: `frontend/admin.html:412`, `frontend/admin.html:525`, `frontend/report_print.html:25`
- Function/Endpoint: Admin UI

#### Evidence

Admin key is read from and written to `localStorage`.

#### Root Cause

Static frontend uses bearer key directly in browser storage.

#### Safe Exploitation Scenario

Any XSS in admin origin can read `pai_admin_key` and call admin APIs.

#### Impact

Full admin API compromise within key permissions.

#### Recommendation

Replace with server-side session and HttpOnly Secure SameSite cookie; add CSP.

#### Suggested Patch

Implement `/admin/login` that validates key once and sets signed HttpOnly session cookie.

#### Functional Impact

Admin UI fetch helper must use cookie/session instead of explicit header key.

#### Verification

Browser devtools should not show admin secret in localStorage/sessionStorage.

### [SEC-005] Raw AI/STT Output Logged

- Severity: Medium
- Status: Fixed
- CWE: CWE-532
- OWASP: A09:2021 Security Logging and Monitoring Failures
- File: `backend/routers/interview.py`
- Lines: around L215
- Function/Endpoint: `POST /interview/evaluate-step`

#### Evidence

The handler prints raw LLM response, which can include normalized candidate transcript and follow-up reasoning.

#### Root Cause

Debug logging left in runtime path.

#### Safe Exploitation Scenario

Server logs collect candidate personal data and interview answers, then logs are shared or retained longer than candidate data.

#### Impact

Confidentiality and compliance risk.

#### Recommendation

Remove raw payload logs or gate behind redacted debug mode.

#### Suggested Patch

Log only request id, question number, and model status; never full transcript/CV/LLM output.

#### Functional Impact

Reduced debug detail in production.

#### Verification

Submit an interview answer and confirm logs contain no answer text.

### [SEC-006] Missing Security Headers And CSP

- Severity: Medium
- Status: Fixed
- CWE: CWE-693
- OWASP: A05:2021 Security Misconfiguration
- File: `backend/main.py`
- Function/Endpoint: all HTTP responses

#### Evidence

No middleware found setting CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, or frame controls.

#### Root Cause

FastAPI app serves static frontend without response security header middleware.

#### Recommendation

Add middleware for production headers. CSP needs care because the current frontend uses inline scripts.

### [SEC-007] Upload Validation Lacks Magic Bytes And Malware Checks

- Severity: Low
- Status: Confirmed
- CWE: CWE-434
- OWASP: A05:2021 Security Misconfiguration
- File: `backend/security.py`
- Function/Endpoint: CV/audio uploads

#### Evidence

Upload helper validates extension/content-type mapping and size, but not file signatures or malicious document content.

#### Recommendation

Add magic-byte validation for PDF/DOCX/audio, document parser sandboxing, and malware scanning for production.

### [SEC-008] Docker Runs As Root And Lacks Hardening

- Severity: Low
- Status: Confirmed
- CWE: CWE-250
- File: `Dockerfile`, `docker-compose.yml`

#### Evidence

No `USER` directive or hardening options found.

#### Recommendation

Run as non-root, drop capabilities, set `no-new-privileges`, pin base image by digest, add read-only filesystem where possible.

## Dependency Status

- `npm audit`: 0 vulnerabilities.
- `pip-audit`: not installed; Python dependency CVE scan not completed.
- Python requirements are unpinned.

## Files Needing Fixes

- `backend/routers/webhook.py`
- `backend/routers/api_v1.py`
- `backend/routers/proctoring.py`
- `backend/routers/interview.py`
- `backend/main.py`
- `backend/security.py`
- `frontend/admin.html`
- `frontend/report_print.html`
- `Dockerfile`
- `docker-compose.yml`
- `.gitignore`
- `requirements.txt`
