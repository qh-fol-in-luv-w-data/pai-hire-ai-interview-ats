# Manual Runtime Checks

Run these checks in a staging environment, not production.

1. Confirm `.env`, `.git`, sqlite DB, logs, and key files are not reachable via ngrok/public domain.
2. Try candidate slot before start, during slot, after end, and after malformed timezone inputs.
3. Try brute forcing `APP-XXXXXXXX` on candidate/proctoring endpoints with rate-limit monitoring.
4. Verify proctoring webhook rejects missing/wrong secret.
5. Verify `/api/webhook/generate-deep-analysis` cannot call localhost, private IPs, cloud metadata, or redirected private targets after SSRF fix.
6. Upload fake PDF/DOCX by extension only, SVG, HTML, oversized files, and malformed files.
7. Test XSS markers in candidate name/email/JD/admin notes/candidate reply and inspect every `innerHTML` render.
8. Confirm admin key is not exposed in browser storage after moving to HttpOnly session/cookie.
9. Confirm server logs do not include raw transcripts, CV text, LLM output, tokens, SMTP credentials, or webhook URLs with secrets.
10. Run Python dependency audit in CI once dependencies are pinned.
