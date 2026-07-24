# Dependency Review

## JavaScript

- `npm audit --json` completed successfully after network access.
- Result: 0 vulnerabilities across npm dependencies.
- `package.json` currently declares `puppeteer` only.

## Python

- `requirements.txt` uses unpinned dependencies:
  - `fastapi`
  - `uvicorn[standard]`
  - `python-dotenv`
  - `python-multipart`
  - `httpx`
  - `openai`
  - `edge-tts`
  - `python-docx`
  - `pdfplumber`
  - `pypdf`
- `pip-audit` is not installed in this environment, so CVE scan for Python packages was not completed.

## Risk

- Unpinned Python dependencies create reproducibility and supply-chain risk.
- Recommended: pin versions with hashes or generate a lock file, then run `pip-audit -r requirements.txt`.
