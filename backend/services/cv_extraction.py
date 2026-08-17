"""Trích xuất các thông tin liên hệ cơ bản từ nội dung CV."""
import re


EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?84|0)(?:[ .-]?\d){8,10}")
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)

KNOWN_SKILLS = (
    "python", "javascript", "typescript", "java", "c++", "c#", "sql", "react",
    "node.js", "nodejs", "vue", "angular", "docker", "kubernetes", "aws", "azure",
    "gcp", "git", "figma", "excel", "power bi", "tableau", "selenium", "rest api",
    "machine learning", "tensorflow", "photoshop", "photoshop", "communication",
)


def extract_candidate_info(text: str, fallback_name: str = "", fallback_email: str = "", fallback_phone: str = "") -> dict:
    text = text or ""
    compact = re.sub(r"\s+", " ", text).strip()
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))
    phones = []
    for raw in PHONE_RE.findall(text):
        normalized = re.sub(r"[^\d+]", "", raw)
        if normalized not in phones:
            phones.append(normalized)
    urls = list(dict.fromkeys(URL_RE.findall(text)))

    lines = [re.sub(r"\s+", " ", line).strip(" •|-\t") for line in text.splitlines()]
    lines = [line for line in lines if line]
    name = fallback_name.strip()
    if not name:
        for line in lines[:12]:
            low = line.lower()
            if len(line) <= 80 and not EMAIL_RE.search(line) and not PHONE_RE.search(line) and not URL_RE.search(line):
                if not any(word in low for word in ("curriculum", "resume", "cv", "email", "phone", "điện thoại", "linkedin", "address", "địa chỉ")):
                    name = line
                    break

    skills = []
    low_text = compact.lower()
    for skill in KNOWN_SKILLS:
        if skill.lower() in low_text:
            skills.append(skill)

    return {
        "name": name or None,
        "email": (fallback_email.strip() or (emails[0] if emails else None)),
        "phone": (fallback_phone.strip() or (phones[0] if phones else None)),
        "emails": emails,
        "phones": phones,
        "links": urls,
        "skills": skills,
    }
