# Security Scan Report

Scan date: 2026-07-22
Source checklist: `security-scan.md`
Mode: scan plus scoped remediation pass.

## Remediation Pass - 2026-07-22

Current user scope: continue with `ats_phongvan` and VoiceApp backup only; stop further CT_DataLake remediation.

Code-level fixes applied and validated for `ats_phongvan`:

- `SEC-008`: `ats_phongvan/interview_api.py` legacy read/list/review endpoints now require the admin key.
- `SEC-010`: Upload guards were added to `ats_phongvan` CV/audio upload paths.
- `SEC-011`: Proctoring webhook now requires a shared secret and validates key fields.
- `SEC-012`: `frontend/interview.html` slot error message is escaped before inserting into HTML.
- `SEC-016`: `.gitignore`/`.dockerignore` rules were expanded to keep local secrets/runtime artifacts out of source context.
- `SEC-017`: Temporary interview pushback audio is no longer publicly mounted; generated URLs are signed and served with `Cache-Control: no-store`.
- Proctoring session frontend path now matches backend route: `/api/v1/proctoring/session`.

Validation run for `ats_phongvan`:

- FastAPI TestClient: `/health`, `/interview`, `/apply`, `/admin`.
- Admin guard: `/interviews` rejects missing key and works with `X-Admin-Key`.
- Legacy `interview_api.py`: health works; protected list/detail routes reject missing key and work with key.
- Signed temp audio: valid token serves audio; invalid token is rejected.
- Proctoring webhook/session routes return expected status codes.
- `frontend/interview.html` script blocks parse successfully with Node.

Operational items still required outside code:

- `SEC-001` to `SEC-003`: rotate/revoke all secrets already exposed in `.env`, backup archives, site configs or database dumps. Code changes cannot invalidate leaked keys by themselves.
- `SEC-001`: move/delete/encrypt the VoiceApp backup artifacts and disable insecure Frappe site settings in the real deployed site config.
- `SEC-003`: keep local `.env` files out of shared source; `.gitignore`/`.dockerignore` now help prevent future inclusion, but existing local secret files were not deleted to avoid breaking local runtime.
- CT_DataLake remediation is intentionally out of the active scope after the latest user instruction.

## Scope Assumptions

- Voice app source was interpreted as `/Users/_qh.fol_/Desktop/VoiceApp_Backup`, which contains a Frappe/site backup rather than code.
- `ats_phongvan` is the current workspace `/Users/_qh.fol_/ats_phongvan`.
- `2as-employee-assessment-feat-code-cua-An` is `/Users/_qh.fol_/Downloads/2as-employee-assessment-feat-code-cua-An`.
- `ai_ats` is `/Users/_qh.fol_/AI_ATS`.
- `ct_datalake` is `/Users/_qh.fol_/CT_DataLake-main`.

## Summary Counts

| Severity | Count |
|---|---:|
| Critical | 5 |
| High | 7 |
| Medium | 5 |
| Low | 0 |

## Findings Table

| ID | Finding | Severity | Module | File | Status | Priority |
|---|---|---|---|---|---|---|
| SEC-001 | VoiceApp backup contains database dump, private files and site config secrets | Critical | VoiceApp_Backup | `/Users/_qh.fol_/Desktop/VoiceApp_Backup/20260519_215828-ct-datalake_localhost-site_config_backup.json; database.sql.gz` | Confirmed | P0 |
| SEC-002 | Real application secrets are present in AI_ATS workspace .env | Critical | AI_ATS | `/Users/_qh.fol_/AI_ATS/.env` | Confirmed | P0 |
| SEC-003 | Real application secrets are present in ats_phongvan workspace .env | Critical | ats_phongvan | `/Users/_qh.fol_/ats_phongvan/.env` | Confirmed | P0 |
| SEC-004 | Real OpenAI key is present in CT_DataLake app .env | Critical | ct_datalake | `/Users/_qh.fol_/CT_DataLake-main/apps/ct_datalake/.env` | Confirmed | P0 |
| SEC-005 | CT_DataLake candidate search, JD matching and document drafting are guest-accessible | Critical | ct_datalake | `ct_datalake/api.py:69,111,158,185,237,356,476,489` | Confirmed | P0 |
| SEC-006 | CT_DataLake local FastAPI exposes sensitive AI/search APIs without auth and uses wildcard CORS with credentials | High | ct_datalake | `ct_datalake/fastapi_app.py:28-34,58-104` | Confirmed | P1 |
| SEC-007 | 2AS HR OCR/review/export endpoints are guest-accessible and rely on client-provided session IDs | High | 2as-employee-assessment | `scan_phieu.py:755,1301,1415; scan_sxkd.py:371,428; thu_viec.py:1623,1910,2199` | Confirmed | P1 |
| SEC-008 | ats_phongvan legacy interview_api exposes interview details, listing and review mutation without backend auth | High | ats_phongvan | `interview_api.py:260,283,312,341` | Confirmed | P1 |
| SEC-009 | AI_ATS hardcodes survey answer tokens and disables TLS verification while scraping reports | High | AI_ATS | `report_pipeline.py:31-33,73` | Confirmed | P0 |
| SEC-010 | Public uploads feed LLM/OCR pipelines with extension-only or missing size/magic-byte validation | High | ct_datalake / 2AS | `fastapi_app.py:95-106; ct_datalake/api.py:185-216,356-377; scan_phieu.py:755-789` | Confirmed | P1 |
| SEC-011 | Unauthenticated proctoring webhook can pollute alert data | Medium | ats_phongvan | `backend/routers/proctoring.py:65` | Confirmed | P2 |
| SEC-012 | Dynamic HTML rendering in frontends can become XSS if server/LLM output is attacker-controlled | Medium | 2AS / ats_phongvan | `TaiKy.vue:665; ProbationEval.vue:151; frontend/interview.html:818` | Potential - Manual Verification Required | P2 |
| SEC-013 | CT_DataLake frontend dependencies include high-severity axios/form-data advisories | High | ct_datalake | `frontend/package-lock.json; npm audit output` | Confirmed | P1 |
| SEC-014 | Container configuration lacks hardening and may copy local secrets into images | Medium | ct_datalake | `Dockerfile:18-22; docker-compose.yml:7-15,22-23` | Confirmed | P2 |
| SEC-015 | Guest AI/LLM endpoints lack rate limit, cost guard and prompt-injection boundaries | High | ct_datalake / 2AS | `ct_datalake/api.py:111,158,237,356,476,489; scan_phieu.py:755,1301; thu_viec.py:1910,2199` | Confirmed | P1 |
| SEC-016 | Runtime artifacts and local databases/logs are kept inside ats_phongvan source tree | Medium | ats_phongvan | `ats_phongvan.db; backend/*.db; backend/*.sqlite; ngrok.log` | Confirmed | P2 |
| SEC-017 | Temporary generated interview audio is publicly mounted | Medium | ats_phongvan | `backend/main.py:21` | Confirmed | P2 |

## Top 10 Risks

1. Rotate secrets and secure VoiceApp backup artifacts (`SEC-001`).
2. Rotate/remove real `.env` secrets in AI_ATS, ats_phongvan and CT_DataLake (`SEC-002` to `SEC-004`).
3. Remove guest access from CT_DataLake candidate/LLM endpoints (`SEC-005`).
4. Add auth/rate limits to CT_DataLake local FastAPI (`SEC-006`).
5. Remove guest access/session ID trust from 2AS HR workflows (`SEC-007`).
6. Retire or secure `ats_phongvan/interview_api.py` (`SEC-008`).
7. Remove hardcoded survey tokens and enable TLS verification in AI_ATS (`SEC-009`).
8. Harden uploads and parser pipelines (`SEC-010`).
9. Upgrade CT_DataLake frontend dependencies (`SEC-013`).
10. Add LLM prompt/output/rate/cost controls (`SEC-015`).

## Endpoint Risk Highlights

- CT_DataLake: all `allow_guest=True` search/match/LLM endpoints should be treated as high-risk until protected.
- 2AS: `scan_extract`, `scan_analyze`, `fill_docx`, `review_files`, `chat_review`, `export_excel` need backend auth/ownership decisions.
- ats_phongvan: current backend is partially hardened, but legacy `interview_api.py` and public static temp audio mount need review.

## Files Needing Immediate Review

- `/Users/_qh.fol_/Desktop/VoiceApp_Backup/*`
- `/Users/_qh.fol_/AI_ATS/.env`
- `/Users/_qh.fol_/ats_phongvan/.env`
- `/Users/_qh.fol_/CT_DataLake-main/apps/ct_datalake/.env`
- `/Users/_qh.fol_/CT_DataLake-main/apps/ct_datalake/ct_datalake/api.py`
- `/Users/_qh.fol_/CT_DataLake-main/ct_datalake/fastapi_app.py`
- `/Users/_qh.fol_/Downloads/2as-employee-assessment-feat-code-cua-An/cnb_2as/api/*.py`
- `/Users/_qh.fol_/ats_phongvan/interview_api.py`
- `/Users/_qh.fol_/AI_ATS/report_pipeline.py`

## Detailed Findings


## [SEC-001] VoiceApp backup contains database dump, private files and site config secrets

- Severity: Critical
- Status: Confirmed
- CWE: CWE-200/CWE-522
- OWASP: A01 Broken Access Control / A02 Cryptographic Failures
- Module: VoiceApp_Backup
- File: `/Users/_qh.fol_/Desktop/VoiceApp_Backup/20260519_215828-ct-datalake_localhost-site_config_backup.json; database.sql.gz`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-001: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-002] Real application secrets are present in AI_ATS workspace .env

- Severity: Critical
- Status: Confirmed
- CWE: CWE-798
- OWASP: A01 Broken Access Control / A02 Cryptographic Failures
- Module: AI_ATS
- File: `/Users/_qh.fol_/AI_ATS/.env`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-002: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-003] Real application secrets are present in ats_phongvan workspace .env

- Severity: Critical
- Status: Confirmed
- CWE: CWE-798
- OWASP: A01 Broken Access Control / A02 Cryptographic Failures
- Module: ats_phongvan
- File: `/Users/_qh.fol_/ats_phongvan/.env`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-003: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-004] Real OpenAI key is present in CT_DataLake app .env

- Severity: Critical
- Status: Confirmed
- CWE: CWE-798
- OWASP: A01 Broken Access Control / A02 Cryptographic Failures
- Module: ct_datalake
- File: `/Users/_qh.fol_/CT_DataLake-main/apps/ct_datalake/.env`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-004: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-005] CT_DataLake candidate search, JD matching and document drafting are guest-accessible

- Severity: Critical
- Status: Confirmed
- CWE: CWE-306/CWE-862
- OWASP: A01 Broken Access Control / A02 Cryptographic Failures
- Module: ct_datalake
- File: `ct_datalake/api.py:69,111,158,185,237,356,476,489`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-005: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-006] CT_DataLake local FastAPI exposes sensitive AI/search APIs without auth and uses wildcard CORS with credentials

- Severity: High
- Status: Confirmed
- CWE: CWE-306/CWE-942
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: ct_datalake
- File: `ct_datalake/fastapi_app.py:28-34,58-104`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-006: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-007] 2AS HR OCR/review/export endpoints are guest-accessible and rely on client-provided session IDs

- Severity: High
- Status: Confirmed
- CWE: CWE-306/CWE-639
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: 2as-employee-assessment
- File: `scan_phieu.py:755,1301,1415; scan_sxkd.py:371,428; thu_viec.py:1623,1910,2199`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-007: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-008] ats_phongvan legacy interview_api exposes interview details, listing and review mutation without backend auth

- Severity: High
- Status: Confirmed
- CWE: CWE-306/CWE-862
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: ats_phongvan
- File: `interview_api.py:260,283,312,341`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-008: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-009] AI_ATS hardcodes survey answer tokens and disables TLS verification while scraping reports

- Severity: High
- Status: Confirmed
- CWE: CWE-319/CWE-200
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: AI_ATS
- File: `report_pipeline.py:31-33,73`
- Priority: P0

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-009: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-010] Public uploads feed LLM/OCR pipelines with extension-only or missing size/magic-byte validation

- Severity: High
- Status: Confirmed
- CWE: CWE-434
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: ct_datalake / 2AS
- File: `fastapi_app.py:95-106; ct_datalake/api.py:185-216,356-377; scan_phieu.py:755-789`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-010: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-011] Unauthenticated proctoring webhook can pollute alert data

- Severity: Medium
- Status: Confirmed
- CWE: CWE-345
- OWASP: A05 Security Misconfiguration / A09 Logging and Monitoring Failures
- Module: ats_phongvan
- File: `backend/routers/proctoring.py:65`
- Priority: P2

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-011: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-012] Dynamic HTML rendering in frontends can become XSS if server/LLM output is attacker-controlled

- Severity: Medium
- Status: Potential - Manual Verification Required
- CWE: CWE-79
- OWASP: A05 Security Misconfiguration / A09 Logging and Monitoring Failures
- Module: 2AS / ats_phongvan
- File: `TaiKy.vue:665; ProbationEval.vue:151; frontend/interview.html:818`
- Priority: P2

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-012: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-013] CT_DataLake frontend dependencies include high-severity axios/form-data advisories

- Severity: High
- Status: Confirmed
- CWE: CWE-1395
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: ct_datalake
- File: `frontend/package-lock.json; npm audit output`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-013: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-014] Container configuration lacks hardening and may copy local secrets into images

- Severity: Medium
- Status: Confirmed
- CWE: CWE-250
- OWASP: A05 Security Misconfiguration / A09 Logging and Monitoring Failures
- Module: ct_datalake
- File: `Dockerfile:18-22; docker-compose.yml:7-15,22-23`
- Priority: P2

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-014: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-015] Guest AI/LLM endpoints lack rate limit, cost guard and prompt-injection boundaries

- Severity: High
- Status: Confirmed
- CWE: CWE-770/CWE-20
- OWASP: A01 Broken Access Control / A05 Security Misconfiguration
- Module: ct_datalake / 2AS
- File: `ct_datalake/api.py:111,158,237,356,476,489; scan_phieu.py:755,1301; thu_viec.py:1910,2199`
- Priority: P1

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-015: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-016] Runtime artifacts and local databases/logs are kept inside ats_phongvan source tree

- Severity: Medium
- Status: Confirmed
- CWE: CWE-200
- OWASP: A05 Security Misconfiguration / A09 Logging and Monitoring Failures
- Module: ats_phongvan
- File: `ats_phongvan.db; backend/*.db; backend/*.sqlite; ngrok.log`
- Priority: P2

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-016: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.

## [SEC-017] Temporary generated interview audio is publicly mounted

- Severity: Medium
- Status: Confirmed
- CWE: CWE-200
- OWASP: A05 Security Misconfiguration / A09 Logging and Monitoring Failures
- Module: ats_phongvan
- File: `backend/main.py:21`
- Priority: P2

### Evidence
Static scan found the referenced file/line pattern. Secret values are redacted where applicable.

### Root Cause
Sensitive data or sensitive behavior is exposed without sufficient backend authentication, authorization, input validation, runtime hardening or secret hygiene.

### Safe Exploitation Scenario
An attacker or unauthorized internal user with network or filesystem access could call the endpoint, reuse leaked capability tokens, trigger expensive parser/LLM work, read sensitive HR/candidate data, inject untrusted content into rendered output, or obtain operational secrets from local artifacts/backups.

### Impact
Potential confidentiality impact includes CVs, candidate reports, employee evaluations, private audio/files, API keys and database backups. Integrity impact includes forged review/proctoring/session data. Availability impact includes LLM cost abuse and parser/upload DoS.

### Recommendation
Apply the remediation plan entry for SEC-017: enforce server-side auth/role/ownership, rotate or remove secrets, limit and validate inputs, add rate limits, harden containers and add tests.

### Suggested Patch
Not applied in this scan-only phase. Recommended patch direction: add explicit auth decorators/dependencies, scoped session ownership checks, signed webhook validation, upload guard helpers and secret/config cleanup.

### Functional Impact
May require frontend changes to pass auth tokens/CSRF, migration away from guest workflows, rotation of environment secrets and compatibility testing for dependency upgrades.

### Verification
Add negative tests proving anonymous callers fail, cross-session IDs fail, oversized/invalid uploads fail, signed webhook is required, and dependency audit passes.
