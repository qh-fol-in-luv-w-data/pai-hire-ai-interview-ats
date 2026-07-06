"""
Generate JD files for Entry, Mid, Senior, Manager, Director levels
based on existing Junior JDs using GPT-4o.

Each API call takes 1 Junior JD and returns 5 adapted JDs in one shot.
"""
import os, json, re, time, asyncio
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

JDS_DIR = Path(__file__).parent / "JDs_Detailed"
LEVELS  = ["Entry", "Mid", "Senior", "Manager", "Director"]

LEVEL_CONTEXT = {
    "Entry": {
        "exp": "0–6 tháng (chấp nhận sinh viên mới ra trường, sinh viên năm cuối có thực tập)",
        "scope": "Thực hiện các nhiệm vụ được giao cụ thể dưới sự hướng dẫn sát sao của Senior",
        "edu": "Đang học hoặc vừa tốt nghiệp Cao đẳng/Đại học chuyên ngành liên quan",
        "salary": "Thỏa thuận (dao động 5–10 triệu VNĐ/tháng tùy năng lực)",
        "grow": "Được đào tạo chuyên sâu nội bộ, lộ trình lên Junior sau 6–12 tháng",
    },
    "Mid": {
        "exp": "2–4 năm ở vị trí tương đương, có khả năng làm việc độc lập",
        "scope": "Chủ động xử lý các tác vụ vừa và nhỏ, hỗ trợ onboard và review work của Junior",
        "edu": "Tốt nghiệp Đại học chuyên ngành liên quan",
        "salary": "Thỏa thuận theo năng lực (cạnh tranh so với thị trường)",
        "grow": "Lộ trình lên Senior trong 1–2 năm, cơ hội tham gia các dự án chiến lược",
    },
    "Senior": {
        "exp": "4–7 năm kinh nghiệm, thành thạo chuyên môn sâu, có khả năng thiết kế giải pháp kỹ thuật",
        "scope": "Dẫn dắt kỹ thuật, review architecture, code review, mentoring cho Junior và Mid",
        "edu": "Tốt nghiệp Đại học chuyên ngành liên quan; bằng Thạc sĩ là lợi thế",
        "salary": "Cạnh tranh cao, thỏa thuận theo năng lực; không giới hạn trần lương",
        "grow": "Lộ trình lên Tech Lead / Team Lead / Manager, cơ hội tham gia product ownership",
    },
    "Manager": {
        "exp": "5+ năm kinh nghiệm chuyên môn + 1–2 năm kinh nghiệm quản lý đội nhóm 5–15 người",
        "scope": "Xây dựng và quản lý team, đặt OKR/KPI, phân bổ nguồn lực, báo cáo trực tiếp lên Director/C-level",
        "edu": "Tốt nghiệp Đại học; Thạc sĩ quản trị/chuyên ngành là lợi thế lớn",
        "salary": "Lương cơ bản cạnh tranh + thưởng KPI team; phụ cấp quản lý",
        "grow": "Lộ trình lên Senior Manager / Director, cơ hội mở rộng scope quản lý",
    },
    "Director": {
        "exp": "8+ năm kinh nghiệm; 3–5 năm ở vị trí quản lý cấp cao, điều hành bộ phận hoặc nhiều team",
        "scope": "Định hướng chiến lược bộ phận, kiểm soát ngân sách, xây dựng văn hóa tổ chức, phối hợp với CEO/Board",
        "edu": "Tốt nghiệp Đại học; Thạc sĩ / MBA là bắt buộc hoặc lợi thế cao",
        "salary": "Negotiable — gói lương C-level; bao gồm stock option / ESOP theo kết quả kinh doanh",
        "grow": "Cơ hội tham gia hội đồng quản trị, dẫn dắt expansion hoặc M&A",
    },
}

PROMPT_TEMPLATE = """Bạn là chuyên gia HR viết JD chuyên nghiệp cho thị trường Việt Nam.

Dưới đây là JD chuẩn cho cấp bậc **Junior** của vị trí **{position}** (lĩnh vực: {category}):

---
{junior_jd}
---

Hãy viết JD cho **5 cấp bậc** khác dựa trên JD Junior ở trên.
Mỗi JD phải phản ánh đúng kỳ vọng, trách nhiệm và yêu cầu thực tế của cấp bậc đó.

Cấp bậc & ngữ cảnh:
- **Entry**: Kinh nghiệm {Entry_exp}. Phạm vi: {Entry_scope}
- **Mid**: Kinh nghiệm {Mid_exp}. Phạm vi: {Mid_scope}
- **Senior**: Kinh nghiệm {Senior_exp}. Phạm vi: {Senior_scope}
- **Manager**: Kinh nghiệm {Manager_exp}. Phạm vi: {Manager_scope}
- **Director**: Kinh nghiệm {Director_exp}. Phạm vi: {Director_scope}

Yêu cầu format đầu ra (JSON):
{{
  "Entry": "<nội dung markdown JD đầy đủ cho Entry>",
  "Mid": "<nội dung markdown JD đầy đủ cho Mid>",
  "Senior": "<nội dung markdown JD đầy đủ cho Senior>",
  "Manager": "<nội dung markdown JD đầy đủ cho Manager>",
  "Director": "<nội dung markdown JD đầy đủ cho Director>"
}}

Mỗi JD cần có đủ 4 section:
1. MÔ TẢ CÔNG VIỆC (RESPONSIBILITIES) — 5–8 bullet points phù hợp cấp bậc
2. YÊU CẦU ỨNG VIÊN (REQUIREMENTS)
   2.1. Yêu cầu chuyên môn (Hard Skills) — 4–6 bullet points
   2.2. Kỹ năng mềm & Yêu cầu chung (Soft Skills) — 4–6 bullet points (bao gồm số năm kinh nghiệm)
3. CÔNG CỤ & PHẦN MỀM LÀM VIỆC (TOOLS) — 3–5 items
4. QUYỀN LỢI ĐƯỢC HƯỞNG (BENEFITS) — giống Junior nhưng điều chỉnh {Entry_salary}/{Mid_salary}/{Senior_salary}/{Manager_salary}/{Director_salary}

Viết bằng tiếng Việt, chuyên nghiệp, cụ thể. KHÔNG thêm text giải thích ngoài JSON."""


async def generate_for_position(junior_jd_path: Path, cat_dir: Path, semaphore: asyncio.Semaphore):
    position = junior_jd_path.stem.replace("Junior_", "")
    category = cat_dir.name.split("_(")[0].replace("_", " ")
    junior_jd = junior_jd_path.read_text(encoding="utf-8")

    # Skip if all 5 level files already exist
    existing = [lv for lv in LEVELS if (cat_dir / f"{lv}_{position}.md").exists()]
    if len(existing) == len(LEVELS):
        print(f"  [skip] {position} — all levels exist")
        return

    prompt = PROMPT_TEMPLATE.format(
        position=position.replace("_", " "),
        category=category,
        junior_jd=junior_jd[:4000],
        **{f"{lv}_{k}": v for lv, ctx in LEVEL_CONTEXT.items() for k, v in ctx.items()},
    )

    async with semaphore:
        try:
            print(f"  [gen] {position}...")
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)

            for level in LEVELS:
                if level in data and data[level].strip():
                    out_path = cat_dir / f"{level}_{position}.md"
                    # Build header like Junior JDs
                    header = f"# MÔ TẢ CÔNG VIỆC: {level.upper()} {position.replace('_', ' ').upper()}\n\n**📍 Phòng ban / Lĩnh vực:** {category}\n\n---\n\n"
                    content = data[level].strip()
                    # Remove duplicate H1 if GPT already added one
                    content = re.sub(r'^#\s+MÔ TẢ.*\n', '', content, flags=re.IGNORECASE).strip()
                    out_path.write_text(header + content, encoding="utf-8")
                    print(f"    ✓ {level}_{position}.md")

        except Exception as e:
            print(f"  [ERR] {position}: {e}")


async def main():
    sem = asyncio.Semaphore(5)  # max 5 concurrent API calls
    tasks = []

    for cat_dir in sorted(JDS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for jd_file in sorted(cat_dir.glob("Junior_*.md")):
            tasks.append(generate_for_position(jd_file, cat_dir, sem))

    print(f"Generating JDs for {len(tasks)} positions × 5 levels...")
    await asyncio.gather(*tasks)
    print("\nDone!")

    # Count results
    total = sum(1 for cat in JDS_DIR.iterdir() if cat.is_dir()
                for lv in LEVELS for f in cat.glob(f"{lv}_*.md"))
    print(f"Total new files: {total}")


if __name__ == "__main__":
    asyncio.run(main())
