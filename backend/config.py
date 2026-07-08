import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
import socket
import re

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent  # project root
DB_PATH         = BASE_DIR / "ats_phongvan.db"
OUTPUT_DIR      = BASE_DIR / "outputs" / "interviews"
CV_UPLOAD_DIR   = BASE_DIR / "outputs" / "cv_applications"
JDS_DIR         = BASE_DIR / "JDs_Detailed"
ADMIN_KEY       = os.environ.get("ADMIN_KEY", "admin@2024")
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
PASS_SCORE      = 6.0
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASS       = os.environ.get("SMTP_PASS", "")
def _detect_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

_default_interview_url = f"https://{_detect_local_ip()}:8080/interview"
INTERVIEW_URL   = os.environ.get("INTERVIEW_URL", _default_interview_url)

from fastapi import Header, HTTPException
def require_admin(x_admin_key: str = Header(None)):
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "Unauthorized — sai admin key")

FRONTEND_DIR   = BASE_DIR / "frontend"
TEMP_PUSHBACKS_DIR = BASE_DIR / "outputs" / "temp_pushbacks"
TEMP_PUSHBACKS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUESTION_AUDIO_DIR     = BASE_DIR / "outputs" / "question_audio"
GENERATED_QUESTIONS_DIR = BASE_DIR / "Generated_Questions"
GENERATED_AUDIO_DIR     = BASE_DIR / "Generated_Audio"
QUESTION_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Tên file audio Q01-Q04 trong thư mục Generated_Audio
_GEN_AUDIO_NAMES = {
    "01": "01_General.mp3",
    "02": "02_General.mp3",
    "03": "03_Technical.mp3",
    "04": "04_Technical.mp3",
    "05": "05_Soft Skill.mp3",
    "06": "06_Soft Skill.mp3",
}


def _find_position_files(position_id: str):
    """Tìm file .md câu hỏi và thư mục audio cho position_id (e.g. 'Junior_AIML_Engineer').
    Returns (md_path, audio_dir) hoặc (None, None) nếu không tìm thấy."""
    md_name      = f"{position_id}_Questions.md"
    audio_folder = f"{position_id}_Questions"
    for cat_dir in GENERATED_QUESTIONS_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
        md_path = cat_dir / md_name
        if md_path.exists():
            return md_path, GENERATED_AUDIO_DIR / cat_dir.name / audio_folder
    return None, None


def _parse_q0306(md_path: Path) -> dict:
    """Parse file .md, trả về {01: text, ... 08: text}."""
    questions = {}
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^(\d+)\.\s+\*\*\[.*?\]\*\*\s+(.+)$', line.strip())
        if m:
            num = m.group(1).zfill(2)
            questions[num] = m.group(2).strip()
    return questions

CATEGORY_LABELS = {
    "Công_Nghệ_Thông_Tin_(IT)":                            "Công Nghệ Thông Tin",
    "Kinh_Doanh_&_Bán_Hàng_(Sales_&_Business_Development)":"Kinh Doanh & Bán Hàng",
    "Chuỗi_Cung_Ứng_&_Logistics_(Supply_Chain)":           "Chuỗi Cung Ứng & Logistics",
    "Kỹ_Thuật_&_Sản_Xuất_(Engineering_&_Manufacturing)":   "Kỹ Thuật & Sản Xuất",
    "Marketing_&_Truyền_Thông_(Marketing_&_PR)":           "Marketing & Truyền Thông",
    "Nhân_Sự_&_Hành_Chính_(HR_&_Admin)":                   "Nhân Sự & Hành Chính",
    "Thiết_Kế_&_Sáng_Tạo_(Design_&_Creative)":            "Thiết Kế & Sáng Tạo",
    "Tài_Chính_&_Kế_Toán_(Finance_&_Accounting)":          "Tài Chính & Kế Toán",
}

QUESTION_META = {
    "01": "General",    "02": "General",
    "03": "Technical",  "04": "Technical",
    "05": "Soft Skill", "06": "Soft Skill",
    "07": "Experience", "08": "Experience",
}


# ─────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────
HOD_QUESTIONS_PROMPT = """Bạn là chuyên gia tuyển dụng cấp cao. Dựa trên kết quả phỏng vấn bên dưới, hãy gợi ý 3-5 câu hỏi sâu hơn để trưởng bộ phận (HOD) khai thác thêm trong vòng phỏng vấn tiếp theo.

Vị trí: {position} (cấp bậc: {level})
Kết quả sơ bộ:
{summary}

Yêu cầu:
- Tập trung vào điểm chưa rõ hoặc cần xác minh thêm từ phần đánh giá
- Ưu tiên kỹ năng quan trọng nhất của vị trí mà ứng viên chưa thể hiện rõ
- Câu hỏi phải mở, không có câu trả lời yes/no
- Viết bằng tiếng Việt

Trả về JSON: {{"questions": ["câu 1", "câu 2", ...]}}"""

INTRO_TEMPLATE = (
    "Xin chào! Chào mừng bạn đến với buổi phỏng vấn vị trí {title}. "
    "Buổi phỏng vấn hôm nay gồm 8 câu hỏi, chia làm bốn phần: "
    "Phần một — Giao tiếp chung, gồm 2 câu. "
    "Phần hai — Kỹ thuật chuyên môn, gồm 2 câu. "
    "Phần ba — Kỹ năng mềm, gồm 2 câu. "
    "Phần bốn — Kinh nghiệm thực tế từ CV của bạn, gồm 2 câu. "
    "Với mỗi câu, hãy nhấn nút nghe để nghe câu hỏi, sau đó nhấn ghi âm để trả lời. "
    "Không có giới hạn thời gian — hãy trả lời tự nhiên và đầy đủ nhất có thể. "
    "Chúc bạn phỏng vấn thành công!"
)


SCORE_PROMPT = """Bạn là chuyên gia HR cấp cao, chấm điểm nghiêm khắc. Nhiệm vụ: đánh giá CV theo JD, cho điểm CHÍNH XÁC theo rubric dưới đây.
QUAN TRỌNG: total_score = tổng cộng các sub-score thực tế, KHÔNG được tự ước lượng riêng.

=== JOB DESCRIPTION ===
{jd}

=== CV ỨNG VIÊN ===
{cv}

=== RUBRIC CHẤM (10đ) ===

NHÓM 1 – YẾU TỐ CỨNG (7đ):

1.1 Kinh Nghiệm Làm Việc (3.5đ):
  a) Số năm kinh nghiệm (2đ):
     - Đọc JD xác định số năm yêu cầu Y.
     - CV >= Y năm → 2đ
     - CV >= Y*0.6 → 1đ
     - CV >= Y*0.3 → 0.5đ
     - CV < Y*0.3 → 0đ
     - Nếu JD ghi "fresher" hoặc "không yêu cầu KN": có internship/thực tập ≥ 3 tháng → 2đ; chỉ có project trường → 1đ; không có gì → 0.5đ
  b) Tính liên quan ngành (1đ):
     - Đúng ngành/vai trò → 1đ
     - Liên quan gần (cùng domain) → 0.5đ
     - Liên quan xa → 0.25đ
     - Không liên quan → 0đ
  c) Thành tích cụ thể (0.5đ):
     - Có số liệu/kết quả rõ ràng (%, doanh số, giải thưởng) → 0.5đ
     - Chỉ mô tả công việc chung chung → 0đ

1.2 Học Vấn & Chứng Chỉ (2.5đ):
  a) Bằng cấp (1đ):
     - Đúng yêu cầu JD → 1đ
     - Thấp hơn 1 bậc nhưng bù bằng kinh nghiệm → 0.5đ
     - Không đáp ứng → 0đ
  b) Chuyên ngành (1đ):
     - Đúng ngành JD yêu cầu → 1đ
     - Ngành liên quan → 0.5đ
     - Ngành khác hoàn toàn → 0đ
  c) Chứng chỉ chuyên môn (0.5đ):
     - Có đủ chứng chỉ JD yêu cầu → 0.5đ
     - Có một phần → 0.25đ
     - Không có chứng chỉ liên quan → 0đ

1.3 Kỹ Năng Chuyên Môn (1đ):
  - So sánh kỹ năng CV với danh sách kỹ năng JD yêu cầu:
  - Đáp ứng >= 90% → 1đ
  - Đáp ứng 70–89% → 0.75đ
  - Đáp ứng 50–69% → 0.5đ
  - Đáp ứng 30–49% → 0.25đ
  - Đáp ứng < 30% → 0đ
  - NẾU thiếu kỹ năng bắt buộc (must-have) trong JD → tối đa 0.25đ

NHÓM 2 – YẾU TỐ MỀM (3đ):

2.1 Chất lượng CV (1đ):
  - 0.75–1đ: Bố cục rõ ràng, mô tả súc tích có số liệu, không lỗi chính tả, format nhất quán
  - 0.5đ: Đủ thông tin nhưng thiếu số liệu hoặc mô tả chung
  - 0.25đ: Thiếu nhiều mục, khó đọc
  - 0đ: Quá sơ sài hoặc lộn xộn
  - Mặc định chỉ cho 0.5đ nếu không có lý do rõ để cho cao hơn

2.2 Dự án & Portfolio (1đ):
  - 1đ: Có dự án thực tế (không phải bài tập) với kết quả đo lường được, link demo/GitHub
  - 0.75đ: Có dự án thực tế nhưng thiếu kết quả cụ thể
  - 0.5đ: Chỉ có project trường/khóa học có mô tả rõ
  - 0.25đ: Liệt kê project nhưng không có chi tiết
  - 0đ: Không có project nào
  - Mặc định 0.25đ nếu không rõ

2.3 Kỹ Năng Mềm & Leadership (1đ):
  - 1đ: Có vai trò leadership rõ ràng (team lead, trưởng nhóm) + minh chứng cụ thể
  - 0.75đ: Có kinh nghiệm dẫn nhóm nhỏ hoặc mentor
  - 0.5đ: Tham gia nhóm có đóng góp được ghi nhận
  - 0.25đ: Chỉ đề cập kỹ năng mềm chung (teamwork, communication) không có minh chứng
  - 0đ: Không đề cập
  - Mặc định 0.25đ nếu không rõ ràng

=== CÁCH TÍNH TỔNG ===
total_score = (years + relevance + achievements) + (degree + major + certs) + technical_skills + cv_quality + projects + leadership
Làm tròn đến bội số 0.25 gần nhất.

Chỉ trả về JSON thuần (không markdown, không giải thích):
{{
  "total_score": <tổng các sub-score, làm tròn 0.25>,
  "group1": {{
    "work_experience": {{"years": <0|0.5|1|2>, "relevance": <0|0.25|0.5|1>, "achievements": <0|0.5>}},
    "education": {{"degree": <0|0.5|1>, "major": <0|0.5|1>, "certs": <0|0.25|0.5>}},
    "technical_skills": <0|0.25|0.5|0.75|1>
  }},
  "group2": {{
    "cv_quality": <0|0.25|0.5|0.75|1>,
    "projects": <0|0.25|0.5|0.75|1>,
    "leadership": <0|0.25|0.5|0.75|1>
  }},
  "reasons": {{
    "work_experience": "<Lý do chấm điểm Kinh nghiệm (khoảng 20-30 từ, phân tích rõ năm KN và thành tích)>",
    "education": "<Lý do chấm điểm Học vấn (khoảng 15-20 từ, chỉ rõ bằng cấp, chuyên ngành)>",
    "technical_skills": "<Lý do chấm điểm Kỹ năng chuyên môn (nêu rõ đáp ứng bao nhiêu % JD)>",
    "cv_quality": "<Lý do chấm điểm Chất lượng CV (nêu cụ thể bố cục, lỗi nếu có)>",
    "projects": "<Lý do chấm điểm Dự án (nêu bật dự án có tốt không, kết quả đo lường)>",
    "leadership": "<Lý do chấm điểm Kỹ năng mềm/Leadership (nêu rõ minh chứng)>"
  }},
  "summary": "<80-100 từ tiếng Việt: điểm mạnh cụ thể và điểm yếu cụ thể>",
  "pass": <true nếu total_score >= 6>
}}"""

EVAL_PROMPT = """Bạn là chuyên gia đánh giá phỏng vấn tuyển dụng.

Vị trí ứng tuyển: {position}
Loại câu hỏi: {q_type} (Câu {q_num}/8)
Câu hỏi: {question}

Câu trả lời của ứng viên (chuyển từ giọng nói):
\"\"\"{transcript}\"\"\"

Đánh giá theo đúng 4 mức sau (chọn 1):
- nắm vững   : Hiểu sâu, giải thích rõ, có ví dụ cụ thể, trả lời tự tin đầy đủ
- am hiểu    : Hiểu đúng hướng, giải thích cơ bản được nhưng thiếu chi tiết/ví dụ
- có biết qua: Chỉ biết khái niệm bề mặt, không giải thích sâu hơn được
- không biết : Không biết, câu trả lời sai hoặc không liên quan

Trả về JSON (không markdown):
{{
  "level": "nắm vững" | "am hiểu" | "có biết qua" | "không biết",
  "feedback": "Nhận xét 1-2 câu bằng tiếng Việt, nêu lý do xếp mức này",
  "strengths": "Điểm mạnh của câu trả lời (nếu không có thì để trống)",
  "improvements": "Điểm cần cải thiện (nếu không có thì để trống)",
  "normalized_transcript": "Viết lại câu trả lời dưới dạng văn xuôi rõ ràng, mạch lạc dựa trên ngữ cảnh câu hỏi '{question}': giữ nguyên ý của ứng viên, sửa lỗi STT/chính tả, bỏ từ à/ừm/thì/là/mà dư thừa, giữ đúng thuật ngữ chuyên ngành liên quan đến chủ đề đang hỏi"
}}"""

SOFT_SKILL_EVAL_PROMPT = """Bạn là chuyên gia đánh giá kỹ năng mềm trong tuyển dụng.

Câu hỏi phỏng vấn: {question}

Câu trả lời của ứng viên (chuyển từ giọng nói):
\"\"\"{transcript}\"\"\"

Phân tích định tính câu trả lời — KHÔNG xếp mức, KHÔNG cho điểm số.
Đánh giá về: cách diễn đạt, cấu trúc câu trả lời (có theo STAR/tình huống-hành động-kết quả không), thái độ thể hiện, khả năng tự nhận thức và học hỏi.

Trả về JSON (không markdown):
{{
  "feedback": "Nhận xét tổng quan 2-3 câu bằng tiếng Việt, nêu cụ thể cách ứng viên trả lời",
  "strengths": "Điểm mạnh nổi bật của câu trả lời (để trống nếu không có)",
  "improvements": "Gợi ý cải thiện cụ thể (để trống nếu không cần)",
  "normalized_transcript": "Viết lại câu trả lời dưới dạng văn xuôi rõ ràng, mạch lạc dựa trên ngữ cảnh câu hỏi '{question}': giữ nguyên ý của ứng viên, sửa lỗi STT/chính tả, bỏ từ à/ừm/thì/là/mà dư thừa, thêm dấu câu phù hợp, diễn đạt tự nhiên như người đang kể chuyện/trả lời phỏng vấn"
}}"""

CV_QUESTIONS_PROMPT = """Bạn là HR Interviewer đang chuẩn bị phỏng vấn cho vị trí {position} (cấp bậc: {level}).

CV của ứng viên:
{cv_text}

Tạo đúng 2 câu hỏi phỏng vấn về kinh nghiệm thực tế dựa trực tiếp vào thông tin có trong CV trên.
Yêu cầu:
- Điều chỉnh độ khó/chiều sâu phù hợp với cấp bậc {level} (Entry=cơ bản, Mid=dự án thực tế, Senior/Manager=lãnh đạo/chiến lược)
- Hỏi cụ thể về dự án, công nghệ, hoặc kinh nghiệm thực sự đề cập trong CV (không hỏi chung chung)
- Bắt đầu bằng: "Trong CV bạn có đề cập...", "Bạn từng làm...", "Bạn có kinh nghiệm với..." hoặc tương tự
- Câu hỏi phải giúp ứng viên kể chi tiết hơn về những gì họ đã thực sự làm
- Viết bằng tiếng Việt, ngắn gọn (1-2 câu mỗi câu hỏi)

Trả về JSON (không markdown):
{{"q05": "câu hỏi thứ nhất", "q06": "câu hỏi thứ hai"}}"""

HOD_QUESTIONS_PROMPT = """Bạn là chuyên gia tuyển dụng cấp cao. Dựa trên kết quả phỏng vấn bên dưới, hãy gợi ý 3-5 câu hỏi sâu hơn để trưởng bộ phận (HOD) khai thác thêm trong vòng phỏng vấn tiếp theo.

Vị trí: {position} (cấp bậc: {level})
Kết quả sơ bộ:
{summary}

Yêu cầu:
- Tập trung vào điểm chưa rõ hoặc cần xác minh thêm từ phần đánh giá
- Ưu tiên kỹ năng quan trọng nhất của vị trí mà ứng viên chưa thể hiện rõ
- Câu hỏi phải mở, không có câu trả lời yes/no
- Viết bằng tiếng Việt

Trả về JSON: {{"questions": ["câu 1", "câu 2", ...]}}"""

_DEFAULT_EXPERIENCE = {
    "q07": "Dựa trên CV của ứng viên, hãy tạo 1 câu hỏi sâu về 1 dự án nổi bật nhất hoặc kinh nghiệm thực tế quan trọng nhất của ứng viên, yêu cầu ứng viên mô tả khó khăn và cách giải quyết.",
    "q08": "Dựa trên CV của ứng viên, hãy tạo 1 câu hỏi tình huống thực tế liên quan mật thiết đến công nghệ/nghiệp vụ chính mà ứng viên đã làm, để kiểm tra cách họ áp dụng kiến thức vào thực tế."
}

LEVEL_ORDER = {"nắm vững": 10, "am hiểu": 7.5, "có biết qua": 5, "không biết": 0}

_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

THIRD_PARTY_WEBHOOK_URL = os.environ.get("THIRD_PARTY_WEBHOOK_URL", "")

DEEP_ANALYSIS_PROMPT = """Bạn là một Chuyên gia Tuyển dụng cấp cao. 
Nhiệm vụ của bạn là phân tích sâu CV của ứng viên đối chiếu với Mô tả công việc (JD), sau đó sinh ra chính xác {n} câu hỏi phỏng vấn chuyên sâu (deep analysis).

YÊU CẦU CHO CÁC CÂU HỎI:
1. Phải dựa hoàn toàn vào các dự án, kỹ năng, kinh nghiệm CỤ THỂ mà ứng viên đã ghi trong CV.
2. Phải xoáy sâu vào chuyên môn, cách giải quyết vấn đề, khó khăn vướng mắc thực tế ứng viên đã trải qua.
3. Liên kết chặt chẽ với các yêu cầu cốt lõi của JD.
4. Tránh tuyệt đối các câu hỏi chung chung (ví dụ: "Bạn hãy giới thiệu bản thân", "Điểm mạnh của bạn là gì?").

CV Ứng Viên:
{cv_text}

Mô tả công việc (JD):
{jd_text}

HÃY XUẤT RA DANH SÁCH CÁC CÂU HỎI THEO ĐÚNG ĐỊNH DẠNG JSON. Không kèm giải thích.
"""
