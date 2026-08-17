"""Khung lương gross tham khảo cho thị trường TP.HCM, đơn vị triệu VNĐ/tháng."""
import re

LEVEL_FACTORS = {
    "Entry": 0.72,
    "Junior": 1.0,
    "Mid": 1.32,
    "Senior": 1.68,
    "Manager": 2.15,
    "Director": 3.05,
}

# Dải Junior/early-career làm mốc; cấp bậc được điều chỉnh bằng LEVEL_FACTORS.
ROLE_RANGES = [
    (("ai", "machine learning", "aiml"), (20, 32)),
    (("devops", "data engineer", "cyber", "security"), (18, 30)),
    (("fullstack", "backend"), (16, 27)),
    (("frontend", "mobile developer"), (15, 25)),
    (("data analyst", "business analyst"), (15, 24)),
    (("automation tester",), (15, 24)),
    (("qaqc", "system admin", "uiux"), (13, 22)),
    (("financial analyst", "internal auditor"), (15, 25)),
    (("accountant", "kế toán"), (11, 19)),
    (("maintenance engineer", "mechanical engineer", "qc engineer"), (14, 24)),
    (("warehouse supervisor",), (13, 22)),
    (("procurement", "importexport", "logistics coordinator"), (11, 20)),
    (("b2b sales", "account executive"), (12, 22)),
    (("e-commerce", "brand executive", "digital market", "seo"), (12, 22)),
    (("content creator", "pr executive", "event coordinator"), (10, 18)),
    (("telesales", "sales admin"), (9, 16)),
    (("talent acquisition", "c&b", "l&d"), (11, 20)),
    (("hr admin", "office admin"), (9, 16)),
    (("receptionist",), (8, 13)),
    (("3d artist", "motion graphic"), (12, 22)),
    (("graphic designer", "video editor"), (10, 19)),
]

CATEGORY_RANGES = {
    "công nghệ": (14, 24),
    "tài chính": (12, 21),
    "kỹ thuật": (13, 22),
    "kinh doanh": (10, 19),
    "marketing": (10, 19),
    "chuỗi cung ứng": (10, 18),
    "nhân sự": (9, 17),
    "thiết kế": (10, 19),
}


def market_salary(job_id: str, title: str, category: str) -> str:
    level_match = re.match(r"^(Entry|Junior|Mid|Senior|Manager|Director)_", job_id or "")
    level = level_match.group(1) if level_match else "Junior"
    haystack = f"{job_id} {title}".lower().replace("_", " ")
    base = next((salary for keys, salary in ROLE_RANGES if any(key in haystack for key in keys)), None)
    if base is None:
        category_lower = (category or "").lower()
        base = next((salary for key, salary in CATEGORY_RANGES.items() if key in category_lower), (10, 18))
    factor = LEVEL_FACTORS[level]
    low = max(7, round(base[0] * factor))
    high = max(low + 2, round(base[1] * factor))
    suffix = " + thưởng/KPI" if any(word in haystack for word in ("sales", "telesales", "account executive")) else ""
    return f"{low}–{high} triệu VNĐ/tháng (Gross){suffix}"
