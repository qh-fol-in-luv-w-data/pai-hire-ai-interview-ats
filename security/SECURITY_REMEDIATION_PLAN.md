# Security Remediation Plan

| ID | Action | Priority | Files | Effort | Dependency | Acceptance Criteria |
|---|---|---|---|---:|---|---|
| SEC-001 | Block SSRF in deep-analysis webhook with allowlist and private-IP checks | P0 | `backend/routers/webhook.py`, config | 1d | webhook domain policy | Private/localhost/metadata URLs rejected before background task |
| SEC-002 | Remove `ADMIN_KEY` fallback from external API token | P1 | `backend/routers/api_v1.py`, `.env.example` | 0.5d | deployment env | `/api/v1/*` refuses requests when dedicated API token is absent |
| SEC-003 | Add signed proctoring alert polling token | P1 | `backend/routers/proctoring.py`, `frontend/interview.html` | 1d | token secret | Alerts endpoint rejects app-id-only requests |
| SEC-004 | Replace localStorage admin key with HttpOnly session cookie | P1 | `backend/main.py`, admin auth routes, `frontend/admin.html`, `frontend/report_print.html` | 2d | session secret | Admin secret no longer appears in Web Storage |
| SEC-005 | Remove/redact raw LLM/STT logs | P1 | `backend/routers/interview.py`, services | 0.5d | logging policy | Logs contain ids/status only, no transcript/CV text |
| SEC-006 | Add security headers and CSP plan | P2 | `backend/main.py`, frontend pages | 1d | inline script migration for strict CSP | Headers present on `/admin`, `/interview`, `/apply` |
| SEC-007 | Add magic-byte validation and malware scan hook | P2 | `backend/security.py`, upload routes | 1d | scanner choice | Fake extension uploads rejected |
| SEC-008 | Harden Docker runtime | P3 | `Dockerfile`, `docker-compose.yml` | 0.5d | image user permissions | Container runs non-root with least privilege |
| DEP-001 | Pin Python deps and run `pip-audit` | P2 | `requirements.txt`, CI | 0.5d | lock strategy | CI reports Python CVEs |
| SEC-HYGIENE | Update `.gitignore` and run gitleaks history scan | P0 | `.gitignore`, repo history | 0.5d | gitleaks | Sensitive local files ignored and history scan redacted |

## Order

1. P0: SSRF block and secret hygiene.
2. P1: auth boundary cleanup, proctoring alert token, admin session, logging redaction.
3. P2: headers, upload hardening, dependency audit.
4. P3: Docker hardening.
