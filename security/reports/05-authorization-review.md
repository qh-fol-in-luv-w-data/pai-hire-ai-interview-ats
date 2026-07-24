# Authorization Review

## Findings

- Admin endpoints mostly call `require_admin()` server-side.
- External API report access is all-or-nothing: a valid bearer token can read any `app_id`.
- Candidate endpoints accept `app_ref`/`interview_id` style identifiers; object-level protection depends on ref secrecy rather than a signed token per action.
- SEC-003: proctoring alerts endpoint exposes logs for any valid `APP-XXXXXXXX` without candidate/admin auth.

## IDOR/BOLA Review

| Area | Object | Check | Risk |
|---|---|---|---|
| `/api/v1/report/{app_id}` | CV application/report | bearer token only | Medium |
| `/api/v1/schedule` | CV application | bearer token only | Medium |
| `/candidate/questions?ref=` | CV application | ref exists/status | Medium |
| `/candidate/reply` | CV application | ref exists/status | Medium |
| `/api/v1/proctoring/alerts?app_id=` | Proctoring alerts | app_id exists | Medium |
| `/interview/submit` | Re-interview target | client-supplied `reiv` | High if link leaks |

## Recommendation

- Use signed, short-lived candidate tokens that bind `app_id`, slot token, action, and expiry.
- Use scoped API tokens for third-party clients instead of one global token.
- Add server-side ownership/scope checks for each object action.
