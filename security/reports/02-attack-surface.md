# Attack Surface

| Method | Path | Auth | Role | Ownership | Tenant | Rate limit | Validation | Risk |
|---|---|---|---|---|---|---|---|---|
| GET | `/jobs` | No | Public | N/A | N/A | No | category filter | Low |
| GET | `/jobs/{job_id}` | No | Public | N/A | N/A | No | job resolver | Low |
| POST | `/jobs/{job_id}/apply` | No | Public | N/A | N/A | No | CV type/size | Medium |
| GET | `/candidate/questions` | No | Candidate link | App ref only | N/A | No | app exists | Medium |
| POST | `/candidate/reply` | No | Candidate link | App ref only | N/A | No | text length | Medium |
| GET | `/api/v1/slot/{token}/validate` | No | Candidate link | Slot token | N/A | No | token lookup/time | Medium |
| POST | `/interview/prep` | No | Candidate link | app_ref optional | N/A | No | partial | Medium |
| POST | `/interview/evaluate-step` | No | Candidate session | none | N/A | No | audio type/size | Medium |
| POST | `/interview/submit` | No | Candidate session | app_ref/reiv client supplied | N/A | No | file type/size | High |
| POST | `/interview/incident` | No | Candidate session | app_ref/interview id | N/A | No | bounded text | Medium |
| GET | `/api/v1/proctoring/alerts` | No | Candidate page | app_id only | N/A | No | app_id format | Medium |
| POST | `/api/webhooks/ai-proctoring` | Webhook secret if configured | Third-party | session_id | N/A | No | format checks | Medium |
| POST | `/api/v1/score-cv` | Bearer | External API | none | N/A | No | CV/JD limits | Medium |
| POST | `/api/v1/schedule` | Bearer | External API | app_id exists | N/A | No | time range | Medium |
| GET | `/api/v1/report/{app_id}` | Bearer | External API | app_id only | N/A | No | app exists | Medium |
| POST | `/api/webhook/generate-deep-analysis` | Admin key | Admin | none | N/A | No | weak URL validation | High |
| `/admin/*` | Mixed | Admin | Admin key | N/A | No | varies | Medium |
| GET | `/temp_pushbacks/{filename}` | HMAC query token | Candidate | filename token | N/A | No | path separators blocked | Low |

## High-Risk Areas

- Public candidate interview flow relies on opaque references and lacks rate limiting.
- Admin key is bearer-style and stored in browser localStorage.
- Outbound webhook accepts caller-selected HTTP(S) URL after only syntax validation.
