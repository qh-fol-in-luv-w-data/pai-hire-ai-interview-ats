# Authentication Review

## Current Design

- Admin: `X-Admin-Key` header validated by `require_admin()`.
- External API: `Authorization: Bearer <token>` validated in `backend/routers/api_v1.py`.
- Candidate flows: unauthenticated, using application refs, slot tokens, and interview refs.

## Findings

- SEC-002: External API token falls back to `ADMIN_KEY`.
- SEC-004: Admin key is stored in browser `localStorage`.
- Public candidate endpoints have no brute-force/rate-limit protection.

## Positive Controls

- Admin key comparison uses `hmac.compare_digest`.
- Missing admin key causes server-side failure rather than allowing access.
- Slot tokens are random UUID hex strings.

## Gaps

- No user login/session model, MFA, password reset, cookie hardening, refresh token rotation, or account lockout because the app currently uses shared bearer secrets.
