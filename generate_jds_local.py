"""
Template-based JD generator — không cần API.
Đọc Junior JD → sinh Entry/Mid/Senior/Manager/Director.
"""
import re
from pathlib import Path

JDS_DIR = Path(__file__).parent / "JDs_Detailed"
LEVELS  = ["Entry", "Mid", "Senior", "Manager", "Director"]

# ── Kinh nghiệm yêu cầu theo level ──────────────────────────
EXP_YEARS = {
    "Entry":    "0–6 tháng (ưu tiên sinh viên năm cuối hoặc mới tốt nghiệp có tư duy tốt)",
    "Junior":   "6 tháng–1,5 năm (chấp nhận Fresher có dự án thực tế)",
    "Mid":      "2–4 năm ở vị trí tương đương, có khả năng làm việc độc lập",
    "Senior":   "4–7 năm kinh nghiệm chuyên sâu, có track record dự án thực tế",
    "Manager":  "5+ năm kinh nghiệm chuyên môn và 1–3 năm kinh nghiệm quản lý đội nhóm",
    "Director": "8+ năm kinh nghiệm; 3–5 năm dẫn dắt bộ phận hoặc nhiều team cùng lúc",
}

EDU = {
    "Entry":    "Đang học hoặc vừa tốt nghiệp Cao đẳng/Đại học chuyên ngành liên quan",
    "Junior":   "Tốt nghiệp Cao đẳng/Đại học chuyên ngành liên quan",
    "Mid":      "Tốt nghiệp Đại học chuyên ngành liên quan",
    "Senior":   "Tốt nghiệp Đại học; bằng Thạc sĩ là lợi thế",
    "Manager":  "Tốt nghiệp Đại học; Thạc sĩ Quản trị Kinh doanh (MBA) là lợi thế lớn",
    "Director": "Tốt nghiệp Đại học; Thạc sĩ / MBA là bắt buộc hoặc lợi thế cực cao",
}

SALARY_NOTE = {
    "Entry":    "Thỏa thuận theo năng lực (dao động 5–10 triệu VNĐ/tháng). Xem xét tăng lương sau 6 tháng",
    "Junior":   "Cạnh tranh theo năng lực (Thỏa thuận khi phỏng vấn). Thưởng lương tháng 13 và thưởng KPI",
    "Mid":      "Cạnh tranh so với thị trường, thỏa thuận theo năng lực. Thưởng tháng 13 và thưởng hiệu suất",
    "Senior":   "Cạnh tranh cao, không giới hạn trần lương. Thưởng tháng 13 + thưởng dự án + review lương 6 tháng/lần",
    "Manager":  "Lương cơ bản cạnh tranh + phụ cấp quản lý + thưởng KPI team. Review lương hàng năm",
    "Director": "Gói lương C-level, thỏa thuận trực tiếp với Ban Giám đốc. Bao gồm cổ phần / ESOP theo hiệu quả",
}

GROW_NOTE = {
    "Entry":    "Được đào tạo chuyên sâu nội bộ và hướng dẫn 1-1 từ Senior. Lộ trình lên Junior rõ ràng sau 6–12 tháng",
    "Junior":   "Cơ hội thăng tiến lên Mid-level sau 1–2 năm. Được tham gia các khóa đào tạo nội bộ và bên ngoài",
    "Mid":      "Lộ trình lên Senior trong 1–2 năm. Cơ hội tham gia lead các dự án chiến lược và có team nhỏ",
    "Senior":   "Lộ trình lên Tech Lead / Team Lead / Principal. Cơ hội tham gia product ownership và architecture decision",
    "Manager":  "Lộ trình lên Senior Manager / Head of Department. Cơ hội mở rộng scope và tham gia dự án cấp công ty",
    "Director": "Cơ hội tham gia Hội đồng Quản trị, dẫn dắt chiến lược mở rộng hoặc M&A",
}

# ── Trách nhiệm bổ sung theo level ───────────────────────────
EXTRA_RESP = {
    "Entry": [
        "Thực hiện các nhiệm vụ được giao cụ thể dưới sự hướng dẫn trực tiếp của Senior/Lead.",
        "Học hỏi, tiếp thu kiến thức và kỹ năng qua các buổi training nội bộ và thực tế công việc.",
        "Báo cáo tiến độ công việc hàng ngày/tuần đến người hướng dẫn trực tiếp.",
    ],
    "Junior": [],
    "Mid": [
        "Tự chủ xử lý các task vừa và nhỏ với ít sự giám sát, đảm bảo chất lượng và deadline.",
        "Hỗ trợ onboarding và review work của các thành viên Entry/Junior trong team.",
        "Đề xuất cải tiến quy trình làm việc và đóng góp ý kiến trong các buổi họp team.",
    ],
    "Senior": [
        "Dẫn dắt kỹ thuật (technical leadership) và đưa ra các quyết định thiết kế quan trọng.",
        "Thực hiện code review / work review, đảm bảo chất lượng đầu ra của cả team.",
        "Mentoring và coaching cho Junior và Mid-level, xây dựng năng lực đội ngũ.",
        "Phối hợp với Product/Business để định hình scope và roadmap kỹ thuật/chuyên môn.",
        "Chịu trách nhiệm về kiến trúc giải pháp và đưa ra đánh giá rủi ro kỹ thuật.",
    ],
    "Manager": [
        "Quản lý, phát triển và đánh giá hiệu suất đội ngũ 5–15 người (1-on-1, review định kỳ).",
        "Xây dựng OKR/KPI cho bộ phận, phân bổ nguồn lực và theo dõi tiến độ thực hiện.",
        "Tuyển dụng, onboarding và giữ chân nhân tài; xây dựng văn hóa team tích cực.",
        "Báo cáo định kỳ và phối hợp chặt chẽ với Director/C-level về chiến lược bộ phận.",
        "Quản lý ngân sách vận hành của team; đề xuất đầu tư công cụ và nhân lực.",
        "Giải quyết xung đột nội bộ, đảm bảo môi trường làm việc chuyên nghiệp và hiệu quả.",
    ],
    "Director": [
        "Định hướng chiến lược toàn bộ phận, phối hợp chặt chẽ với CEO và các C-level khác.",
        "Chịu trách nhiệm về ngân sách, headcount plan và các mục tiêu kinh doanh của bộ phận.",
        "Xây dựng và triển khai văn hóa tổ chức, chuẩn mực chuyên môn và quy trình hóa hoạt động.",
        "Đại diện bộ phận trong các cuộc họp cấp cao, đối tác chiến lược và báo cáo Hội đồng Quản trị.",
        "Quản lý đa cấp (Manager → Senior → Mid → Junior), đảm bảo sự đồng nhất trong định hướng.",
        "Dẫn dắt sáng kiến chuyển đổi (transformation), mở rộng quy mô (scaling) hoặc M&A.",
    ],
}

# ── Soft skills bổ sung theo level ───────────────────────────
EXTRA_SOFT = {
    "Entry": [
        "Ham học hỏi, cởi mở với phản hồi và sẵn sàng tiếp thu kiến thức mới liên tục.",
        "Tư duy logic, cẩn thận và chú ý đến chi tiết trong công việc.",
    ],
    "Junior": [],
    "Mid": [
        "Tư duy chủ động, có khả năng giải quyết vấn đề độc lập và đề xuất giải pháp sáng tạo.",
        "Khả năng hướng dẫn và chia sẻ kiến thức cho đồng nghiệp cấp dưới.",
    ],
    "Senior": [
        "Tư duy chiến lược, có tầm nhìn dài hạn về giải pháp và kiến trúc hệ thống.",
        "Kỹ năng lãnh đạo kỹ thuật, truyền đạt và thuyết phục stakeholders ở mọi cấp độ.",
        "Khả năng đưa ra quyết định trong môi trường không chắc chắn và áp lực cao.",
    ],
    "Manager": [
        "Kỹ năng lãnh đạo con người xuất sắc: coaching, feedback, motivation và conflict resolution.",
        "Tư duy dữ liệu (data-driven): đưa ra quyết định dựa trên metrics và KPIs cụ thể.",
        "Khả năng giao tiếp đa cấp, thương lượng và xây dựng mối quan hệ với stakeholders.",
        "Kỹ năng quản lý thay đổi (change management) và xây dựng văn hóa đội nhóm bền vững.",
    ],
    "Director": [
        "Tư duy chiến lược và tầm nhìn kinh doanh vượt trội; có khả năng kết nối chuyên môn với mục tiêu công ty.",
        "Kỹ năng lãnh đạo tổ chức ở quy mô lớn; xây dựng văn hóa và triết lý vận hành.",
        "Khả năng giao tiếp và ảnh hưởng ở cấp C-level, đối tác và nhà đầu tư.",
        "Kinh nghiệm quản lý ngân sách lớn, hoạch định nhân sự và triển khai dự án chiến lược.",
    ],
}

# ── Parse Junior JD ───────────────────────────────────────────
def parse_junior_jd(text: str) -> dict:
    """Trích xuất các section từ Junior JD."""
    sections = {
        "header":        "",
        "responsibilities": [],
        "hard_skills":   [],
        "soft_skills":   [],
        "tools":         [],
        "benefits":      {},
    }

    lines = text.splitlines()
    current = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("# "):
            sections["header"] = stripped
            continue

        if re.match(r"^##\s+1\.", stripped) or "MÔ TẢ CÔNG VIỆC" in stripped.upper():
            current = "responsibilities"
            continue
        if re.match(r"^###\s+2\.1", stripped) or "HARD SKILLS" in stripped.upper() or "CHUYÊN MÔN" in stripped.upper():
            current = "hard_skills"
            continue
        if re.match(r"^###\s+2\.2", stripped) or "SOFT SKILLS" in stripped.upper() or "KỸ NĂNG MỀM" in stripped.upper():
            current = "soft_skills"
            continue
        if re.match(r"^##\s+3\.", stripped) or "CÔNG CỤ" in stripped.upper():
            current = "tools"
            continue
        if re.match(r"^##\s+4\.", stripped) or "QUYỀN LỢI" in stripped.upper():
            current = "benefits_raw"
            sections["benefits_raw"] = []
            continue
        if re.match(r"^##\s+2\.", stripped) or "YÊU CẦU" in stripped.upper():
            current = None
            continue

        if current and stripped.startswith("- "):
            content = stripped[2:].strip()
            if current in ("responsibilities", "hard_skills", "soft_skills", "tools"):
                sections[current].append(content)
            elif current == "benefits_raw":
                sections["benefits_raw"].append(content)

        # Parse benefits key-value
        if current == "benefits_raw" and stripped.startswith("- **"):
            m = re.match(r"^- \*\*(.+?)\*\*[:\s]*(.+)$", stripped)
            if m:
                sections["benefits"][m.group(1).strip()] = m.group(2).strip()

    return sections


def filter_exp_line(lines: list, new_exp: str) -> list:
    """Thay thế dòng kinh nghiệm (X tháng/năm) bằng EXP_YEARS của level."""
    result = []
    replaced = False
    for line in lines:
        low = line.lower()
        if not replaced and any(kw in low for kw in [
            "kinh nghiệm", "năm kinh", "tháng kinh", "fresher", "năm cuối",
            "mới ra trường", "intern", "thực tập", "experience"
        ]):
            result.append(f"Có {new_exp}.")
            replaced = True
        else:
            result.append(line)
    if not replaced:
        result.insert(0, f"Có {new_exp}.")
    return result


def build_jd(level: str, position: str, category: str, parsed: dict) -> str:
    """Build markdown JD cho một level."""
    pos_display = position.replace("_", " ")
    cat_display = category

    # --- Header
    lines = [
        f"# MÔ TẢ CÔNG VIỆC: {level.upper()} {pos_display.upper()}",
        "",
        f"**📍 Phòng ban / Lĩnh vực:** {cat_display}",
        "",
        "---",
        "",
    ]

    # --- Section 1: Responsibilities
    lines.append("## 1. MÔ TẢ CÔNG VIỆC (RESPONSIBILITIES)")
    resp = list(parsed["responsibilities"])  # copy

    # For Manager/Director, replace most Junior responsibilities with level-specific ones
    if level in ("Manager", "Director"):
        resp = EXTRA_RESP[level]
    else:
        resp = resp + EXTRA_RESP[level]

    # For Entry, trim to simpler tasks (remove overly technical lines)
    if level == "Entry":
        resp = resp[:4] + EXTRA_RESP["Entry"]

    for r in resp:
        lines.append(f"- {r}")
    lines.append("")

    # --- Section 2: Requirements
    lines.append("## 2. YÊU CẦU ỨNG VIÊN (REQUIREMENTS)")
    lines.append("### 2.1. Yêu cầu chuyên môn (Hard Skills)")

    hard = list(parsed["hard_skills"])
    # Entry: keep only first 2-3 hard skills (simpler)
    if level == "Entry":
        hard = hard[:3]
        hard.insert(0, EDU[level] + ".")
    elif level == "Manager":
        # Manager: lighter on technical, more on process
        hard = hard[:3]
        hard.insert(0, EDU[level] + ".")
        hard.append("Nắm vững các phương pháp quản lý dự án (Agile/Scrum, OKR, KPI framework).")
        hard.append("Có kinh nghiệm xây dựng và vận hành quy trình chuẩn hóa (SOP) trong đội nhóm.")
    elif level == "Director":
        hard = hard[:2]
        hard.insert(0, EDU[level] + ".")
        hard.append("Kinh nghiệm hoạch định chiến lược bộ phận và quản lý ngân sách quy mô lớn.")
        hard.append("Am hiểu sâu về xu hướng thị trường, cạnh tranh ngành và mô hình kinh doanh.")
        hard.append("Đã từng lead và scale team 15–50 người trở lên.")
    else:
        hard.insert(0, EDU[level] + ".")
        # Senior: add architecture/deep expertise line
        if level == "Senior":
            hard.append("Có kinh nghiệm thiết kế kiến trúc hệ thống/giải pháp và đánh giá rủi ro kỹ thuật.")
            hard.append("Có khả năng nghiên cứu và áp dụng các công nghệ mới vào sản phẩm thực tế.")

    for h in hard:
        lines.append(f"- {h}")
    lines.append("")

    lines.append("### 2.2. Kỹ năng mềm & Yêu cầu chung (Soft Skills)")
    soft = list(parsed["soft_skills"])
    # Replace experience line
    soft = filter_exp_line(soft, EXP_YEARS[level])
    soft = soft + EXTRA_SOFT[level]

    for s in soft:
        lines.append(f"- {s}")
    lines.append("")

    # --- Section 3: Tools
    lines.append("## 3. CÔNG CỤ & PHẦN MỀM LÀM VIỆC (TOOLS)")
    tools = list(parsed["tools"])
    if level in ("Manager", "Director"):
        # Manager/Director use additional management tools
        mgmt_tools = [
            "Jira, Notion, Google Workspace (quản lý dự án và tài liệu nội bộ).",
            "Power BI / Google Data Studio (theo dõi KPI và báo cáo).",
            "Slack, Microsoft Teams (giao tiếp và điều phối công việc).",
        ]
        tools = tools[:2] + mgmt_tools
    for t in tools:
        lines.append(f"- {t}")
    lines.append("")

    # --- Section 4: Benefits
    lines.append("## 4. QUYỀN LỢI ĐƯỢC HƯỞNG (BENEFITS)")
    lines.append(f"- **Mức lương:** {SALARY_NOTE[level]}.")
    lines.append("- **Chế độ bảo hiểm:** Đóng BHXH, BHYT, BHTN đầy đủ theo quy định Luật Lao động ngay sau khi ký HĐLĐ chính thức. Khám sức khỏe định kỳ hàng năm.")
    lines.append("- **Môi trường làm việc:** Trẻ trung, năng động, chuyên nghiệp. Không gian mở, trang bị đầy đủ thiết bị làm việc.")
    lines.append(f"- **Đào tạo & Phát triển:** {GROW_NOTE[level]}.")
    lines.append("- **Phúc lợi khác:** Teambuilding, du lịch thường niên. Phụ cấp ăn trưa, gửi xe, trà/café miễn phí tại pantry công ty.")
    if level in ("Senior", "Manager", "Director"):
        lines.append("- **Thiết bị làm việc:** Được cấp Laptop/thiết bị theo yêu cầu công việc.")
    if level in ("Manager", "Director"):
        lines.append("- **Phụ cấp quản lý:** Phụ cấp trách nhiệm hàng tháng theo cấp bậc.")
    if level == "Director":
        lines.append("- **Cổ phần / ESOP:** Tham gia chương trình cổ phần ưu đãi dành cho cấp lãnh đạo cấp cao theo kết quả kinh doanh.")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────
def main():
    total_written = 0
    total_skipped = 0

    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue

        # Derive clean category label
        cat_label = cat_dir.name.split("_(")[0].replace("_", " ")

        for jd_file in sorted(cat_dir.glob("Junior_*.md")):
            position = jd_file.stem.replace("Junior_", "")
            text     = jd_file.read_text(encoding="utf-8")
            parsed   = parse_junior_jd(text)

            for level in LEVELS:
                out_path = cat_dir / f"{level}_{position}.md"
                if out_path.exists():
                    total_skipped += 1
                    continue

                content = build_jd(level, position, cat_label, parsed)
                out_path.write_text(content, encoding="utf-8")
                print(f"  ✓ {level}_{position}.md")
                total_written += 1

    print(f"\nDone — {total_written} files written, {total_skipped} skipped (already exist)")


if __name__ == "__main__":
    main()
