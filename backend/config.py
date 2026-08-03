import os
from pathlib import Path
from dotenv import load_dotenv
from hmac import compare_digest

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
ADMIN_KEY       = os.environ.get("ADMIN_KEY", "")
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
PASS_SCORE      = 3.0
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASS       = os.environ.get("SMTP_PASS", "")
IMAP_HOST       = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT       = int(os.environ.get("IMAP_PORT", "993"))
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

_server_port = int(os.environ.get("PORT", "8080"))
_default_interview_url = f"http://{_detect_local_ip()}:{_server_port}/interview"
INTERVIEW_URL   = os.environ.get("INTERVIEW_URL", _default_interview_url)

PROCTORING_API_URL = os.environ.get("PROCTORING_API_URL", "http://127.0.0.1:8003/api/v1")
PROCTORING_API_KEY = os.environ.get("PROCTORING_API_KEY", "")
PROCTORING_EMBED_PUBLIC_BASE = os.environ.get("PROCTORING_EMBED_PUBLIC_BASE", "https://service.ctpai.vn/detection/")
PROCTORING_ALERT_THRESHOLD_SECONDS = float(os.environ.get("PROCTORING_ALERT_THRESHOLD_SECONDS", "2"))
PROCTORING_WEBHOOK_SECRET = os.environ.get("PROCTORING_WEBHOOK_SECRET", "")
PROCTORING_WEBHOOK_REQUIRE_SECRET = os.environ.get("PROCTORING_WEBHOOK_REQUIRE_SECRET", "true").lower() not in {"0", "false", "no"}
PUBLIC_WEBHOOK_DOMAIN = os.environ.get("PUBLIC_WEBHOOK_DOMAIN", f"http://{_detect_local_ip()}:{_server_port}")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        f"http://localhost:{_server_port},http://127.0.0.1:{_server_port},{PUBLIC_WEBHOOK_DOMAIN}",
    ).split(",")
    if origin.strip()
]

from fastapi import Header, HTTPException
def require_admin(x_admin_key: str = Header(None)):
    if not ADMIN_KEY:
        raise HTTPException(500, "ADMIN_KEY chưa được cấu hình")
    if not x_admin_key or not compare_digest(x_admin_key, ADMIN_KEY):
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

QUESTIONS_BANK = {
    "01": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_A", "is_dynamic": False, "text": "Theo anh/chị, đâu là 03 kỹ năng chuyên môn quan trọng nhất để làm tốt vị trí này? Vì sao?" },
    "02": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị tự đánh giá mức độ thành thạo của bản thân với từng kỹ năng bắt buộc trong JD như thế nào (theo thang cơ bản/thành thạo/chuyên sâu)?" },
    "03": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_B", "is_dynamic": True, "text": "JD của vị trí yêu cầu kỹ năng [kỹ năng chính trong JD]. Anh/chị hãy chia sẻ một tình huống thực tế đã sử dụng kỹ năng này và kết quả đạt được." },
    "04": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_B", "is_dynamic": True, "text": "JD yêu cầu [kỹ năng chính trong JD]. Nếu CV của anh/chị có kinh nghiệm liên quan hoặc có thể chuyển đổi sang kỹ năng này, hãy mô tả bằng chứng cụ thể; nếu chưa có, anh/chị sẽ bù đắp khoảng trống như thế nào?" },
    "05": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_C", "is_dynamic": True, "text": "Nếu không có sẵn công cụ/tài nguyên quen thuộc, anh/chị sẽ vận dụng kỹ năng [kỹ năng JD] như thế nào để vẫn hoàn thành công việc đúng chất lượng?" },
    "06": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_C", "is_dynamic": False, "text": "Anh/chị có thể nêu một chỉ số hoặc kết quả cụ thể để chứng minh mức độ thành thạo kỹ năng vừa chia sẻ không?" },
    "07": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_D", "is_dynamic": False, "text": "Đưa 1 bài tập/tình huống chuyên môn thực tế đang xảy ra tại phòng ban, yêu cầu ứng viên nêu hướng xử lý ngắn gọn để xác nhận mức độ thành thạo kỹ năng thực tế." },
    "08": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hãy giới thiệu ngắn gọn về quá trình làm việc, vai trò và trách nhiệm chính qua từng vị trí đã đảm nhận." },
    "09": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_B", "is_dynamic": True, "text": "Dựa trên CV, anh/chị có kinh nghiệm [số năm] năm ở vị trí [chức danh]. Kinh nghiệm nào liên quan trực tiếp nhất đến trách nhiệm trong JD này, và phần nào còn là khoảng cách cần bù đắp?" },
    "10": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_B", "is_dynamic": False, "text": "Nếu được nhận vào vị trí này, trong 2 tuần đầu tiên anh/chị sẽ ưu tiên tìm hiểu và triển khai những việc gì để bắt nhịp công việc dựa trên kinh nghiệm đã có?" },
    "11": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_C", "is_dynamic": True, "text": "Vị trí này yêu cầu [trách nhiệm chính trong JD]. Trong các kinh nghiệm ở CV, phần nào liên quan nhất với yêu cầu đó, khó khăn lớn nhất là gì và anh/chị đã xử lý như thế nào?" },
    "12": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_C", "is_dynamic": True, "text": "Một số kinh nghiệm của anh/chị đang nghiêng về [mảng A], trong khi vị trí này yêu cầu nhiều về [mảng B]. Anh/chị đánh giá khoảng cách này như thế nào và sẽ bù đắp ra sao?" },
    "13": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hãy chia sẻ về chuyên ngành đào tạo và các chứng chỉ nghề nghiệp liên quan trực tiếp đến vị trí đang ứng tuyển." },
    "14": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_B", "is_dynamic": True, "text": "CV thể hiện anh/chị tốt nghiệp [chuyên ngành/trường]. Anh/chị đã áp dụng kiến thức được đào tạo vào công việc thực tế như thế nào?" },
    "15": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_C", "is_dynamic": False, "text": "Nếu chuyên ngành đào tạo của anh/chị không hoàn toàn trùng khớp với yêu cầu JD, anh/chị đã bổ sung kiến thức/chứng chỉ liên quan bằng cách nào để đáp ứng công việc?" },
    "16": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_A", "is_dynamic": True, "text": "Anh/chị đã có kinh nghiệm làm việc trong ngành [ngành nghề theo JD] chưa? Nếu chưa, anh/chị đánh giá ngành mình từng làm có điểm gì tương đồng với ngành này?" },
    "17": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_B", "is_dynamic": True, "text": "CV cho thấy anh/chị chủ yếu làm việc trong lĩnh vực [ngành trong CV], trong khi vị trí này thuộc lĩnh vực [ngành JD]. Anh/chị dự kiến sẽ thích nghi với sự khác biệt này như thế nào?" },
    "18": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_C", "is_dynamic": True, "text": "Nếu gặp một vấn đề đặc thù của ngành [ngành JD] mà anh/chị chưa từng xử lý trước đây, anh/chị sẽ tiếp cận và tìm hiểu theo phương pháp nào?" },
    "19": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị mong muốn phát triển năng lực gì trong 6 -12 tháng tới nếu gia nhập CT Group? Anh/chị sẽ đo lường sự tiến bộ đó như thế nào?" },
    "20": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": True, "text": "Dựa trên lộ trình trong CV, những trách nhiệm nào đang hỗ trợ trực tiếp cho yêu cầu của JD này, và trách nhiệm nào còn thiếu so với vị trí ứng tuyển?" },
    "21": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": True, "text": "Nếu lộ trình trong CV chưa trùng với vị trí đang ứng tuyển, điều gì khiến anh/chị muốn chuyển sang hướng này và anh/chị đã chuẩn bị năng lực liên quan đến JD ra sao?" },
    "22": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_C", "is_dynamic": True, "text": "Trong CV có giai đoạn [khoảng thời gian ít thay đổi chức danh/vai trò]. Anh/chị có thể chia sẻ rõ hơn lý do và những gì đã tích lũy được trong giai đoạn đó không?" },
    "23": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_A", "is_dynamic": False, "text": "Hãy chia sẻ một thành tích hoặc dự án/công việc mà anh/chị tự đánh giá là nổi bật nhất trong thời gian gần đây. Vai trò cụ thể của anh/chị trong kết quả đó là gì?" },
    "24": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_B", "is_dynamic": True, "text": "Trong các thành tích ở CV, thành tích nào liên quan trực tiếp nhất đến kết quả kỳ vọng của JD này? Kết quả đó được đo lường như thế nào và anh/chị đóng góp phần nào?" },
    "25": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_B", "is_dynamic": False, "text": "Hãy chia sẻ một kết quả cụ thể mà anh/chị đạt được vượt hơn yêu cầu ban đầu, được đo lường bằng chỉ số, dữ liệu hoặc phản hồi cụ thể." },
    "26": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_C", "is_dynamic": True, "text": "Anh/chị vừa đề cập thành tích [thành tích]. Anh/chị có thể nêu một chỉ số cụ thể (số liệu, %, mốc thời gian) để chứng minh kết quả này không?" },
    "27": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_C", "is_dynamic": False, "text": "Trong thành tích đó, phần việc nào do anh/chị trực tiếp phụ trách, phần nào do đội nhóm hỗ trợ?" },
    "28": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_D", "is_dynamic": True, "text": "AI đang ghi nhận thành tích [thành tích ứng viên nêu] nhưng chưa đủ minh chứng định lượng. Đề nghị HOD hỏi thêm để xác nhận mức độ đóng góp thực tế và độ tin cậy của số liệu." },
    "29": { "type": "Soft Skill", "label": "Tiêu chí 07", "group": "Nhóm_A", "is_dynamic": False, "text": "Trong môi trường làm việc tốc độ cao, nhiều yêu cầu thay đổi nhanh, anh/chị thường quản lý công việc, deadline và áp lực như thế nào?" },
    "30": { "type": "Soft Skill", "label": "Tiêu chí 07", "group": "Nhóm_B", "is_dynamic": True, "text": "JD yêu cầu [kỹ năng mềm/hành vi cần có]. Trong CV có tình huống nào liên quan đến kỹ năng này không? Hãy chia sẻ bối cảnh, hành động cá nhân và kết quả đạt được." },
    "31": { "type": "Soft Skill", "label": "Tiêu chí 07", "group": "Nhóm_B", "is_dynamic": False, "text": "Hãy chia sẻ một tình huống anh/chị từng phải xử lý mâu thuẫn hoặc bất đồng trong nhóm làm việc. Anh/chị đã tiếp cận và giải quyết như thế nào?" },
    "32": { "type": "General", "label": "Tiêu chí 08", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hãy giới thiệu ngắn gọn về bản thân bằng ngoại ngữ theo yêu cầu của vị trí (ví dụ: tiếng Anh) trong khoảng 1 phút." },
    "33": { "type": "General", "label": "Tiêu chí 08", "group": "Nhóm_B", "is_dynamic": True, "text": "CV thể hiện anh/chị có chứng chỉ [chứng chỉ ngoại ngữ trong CV]. Anh/chị sử dụng ngoại ngữ này trong công việc hàng ngày ở mức độ nào (đọc hiểu tài liệu, giao tiếp, thuyết trình, đàm phán)?" },
    "34": { "type": "General", "label": "Tiêu chí 08", "group": "Nhóm_C", "is_dynamic": False, "text": "Nếu phải trao đổi trực tiếp bằng ngoại ngữ với đối tác/khách hàng nước ngoài trong một tình huống phát sinh gấp, anh/chị sẽ chuẩn bị và xử lý như thế nào?" },
    "35": { "type": "General", "label": "Tiêu chí 09", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hình dung mình sẽ gắn bó với vị trí này trong bao lâu? Những yếu tố nào có thể khiến anh/chị cân nhắc rời đi sớm?" },
    "36": { "type": "General", "label": "Tiêu chí 09", "group": "Nhóm_B", "is_dynamic": True, "text": "Trong CV có giai đoạn [khoảng thời gian/chuyển việc nhanh/khoảng trống nghề nghiệp]. Anh/chị có thể chia sẻ rõ hơn về lý do thay đổi và bài học rút ra không?" },
    "37": { "type": "General", "label": "Tiêu chí 09", "group": "Nhóm_C", "is_dynamic": False, "text": "Mức lương kỳ vọng/thời gian nhận việc/địa điểm làm việc của anh/chị hiện có điểm nào cần trao đổi thêm để phù hợp với yêu cầu vị trí không?" },
    "38": { "type": "General", "label": "Tiêu chí 09", "group": "Nhóm_D", "is_dynamic": True, "text": "AI đang cảnh báo rủi ro [điểm rủi ro về mức độ ổn định]. Đề nghị HOD/chuyên gia hỏi thêm để xác nhận rủi ro này có đáng kể hay không trước khi ra quyết định." },
    "39": { "type": "General", "label": "Tiêu chí 10", "group": "Nhóm_A", "is_dynamic": False, "text": "Có thông tin nào trong CV, hồ sơ ứng tuyển hoặc câu trả lời trước đó mà anh/chị muốn bổ sung/làm rõ thêm không?" },
    "40": { "type": "General", "label": "Tiêu chí 10", "group": "Nhóm_D", "is_dynamic": False, "text": "Trong 3 năng lực quan trọng nhất của vị trí này, anh/chị đánh giá ứng viên đang mạnh/yếu ở đâu? Có ví dụ nào trong buổi phỏng vấn thể hiện điều đó? (HOD đề xuất Hire/Hold/Reject kèm lý do ngắn gọn)." },
}

# Cấu hình số lượng câu hỏi tối đa cho từng phần (Theo bộ khung câu hỏi AI Interview)
INTERVIEW_QUESTION_LIMITS = {
    "PART_1_DEFAULT": 11,       # Phần 1: Nhóm câu hỏi mặc định cho tất cả ứng viên
    "PART_2_GENERATED": 7,      # Phần 2: Nhóm câu hỏi AI tạo dựa trên CV, JD (5-7 câu)
    "PART_3_FOLLOW_UP": 5       # Phần 3: Nhóm câu hỏi AI đào sâu (3-5 câu)
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
    "Buổi phỏng vấn hôm nay gồm 40 câu hỏi, kiểm tra toàn diện 10 tiêu chí theo khung năng lực AI. "
    "Hệ thống sẽ hỏi bạn về các kinh nghiệm thực tế, chuyên môn, thành tích nổi bật cũng như cách bạn xử lý khó khăn. "
    "Với mỗi câu, hãy nhấn nút nghe để nghe câu hỏi, sau đó nhấn ghi âm để trả lời. "
    "Không có giới hạn thời gian — hãy trả lời tự nhiên, nêu ví dụ hoặc số liệu thực tế càng cụ thể càng tốt. "
    "Chúc bạn phỏng vấn thành công!"
)


SCORE_PROMPT = """Bạn là chuyên gia AI (PAI Engine) đóng vai trò Chuyên gia Tuyển dụng cấp cao.
Nhiệm vụ của bạn là đánh giá CV của ứng viên so với Mô tả công việc (JD), cho điểm CHÍNH XÁC theo 10 tiêu chí dưới đây.
Mỗi tiêu chí chấm theo THANG 1–5 (số nguyên, KHÔNG chấm số lẻ), sau đó hệ thống sẽ quy đổi ra tổng điểm 10 theo trọng số.

QUY TẮC CHẤM ĐIỂM (CỰC KỲ QUAN TRỌNG):
1. Chấm theo hướng TUYỂN DỤNG THẬN TRỌNG. Mức 5 là trường hợp hiếm, chỉ dành cho CV gần như khớp JD, có thành tích định lượng mạnh và có thể làm ngay.
2. Không suy diễn tốt cho ứng viên. Chỉ cho điểm dựa trên bằng chứng xuất hiện trong CV/JD. Nếu CV không nêu rõ một kỹ năng/kinh nghiệm/thành tích, xem là thiếu minh chứng và KHÔNG được chấm ở mức cao.
3. Với các tiêu chí có mốc "cứng" (số năm, bằng cấp, chứng chỉ, %): bám sát đúng mốc, không suy diễn co giãn.
   Với các tiêu chí "mềm" (thành tích, kỹ năng mềm, lộ trình phát triển, đánh giá tổng thể): chấm theo CHẤT LƯỢNG minh chứng, không có mốc số cứng.
4. Nếu một tiêu chí thiếu minh chứng rõ ràng, không được cho điểm ở mức 5 hoặc 4 của tiêu chí đó — tối đa mức 3.
5. Trong `reasons`, luôn ghi rõ bằng chứng đã dùng và lý do trừ điểm/rủi ro chính. Không được viết chung chung kiểu "phù hợp tốt" nếu thiếu dẫn chứng.
6. NGUYÊN TẮC CHẤM ĐIỂM TỐI ĐA: Nếu trong phần nhận xét (reasons) của một tiêu chí, bạn kết luận "Không có điểm trừ" hoặc không tìm thấy bất kỳ điểm yếu nào, bạn BẮT BUỘC phải chấm mức 5/5 cho tiêu chí đó. Không được tự ý bớt điểm nếu không có lý do trừ cụ thể.
7. Mức 1 luôn là mốc "hoàn toàn không liên quan / trái ngành hoàn toàn / không có minh chứng" — không dùng mức 1 chỉ vì thiếu một vài chi tiết nhỏ.

=== JOB DESCRIPTION ===
{jd}

=== CV ỨNG VIÊN ===
{cv}

=== KHUNG ĐÁNH GIÁ VÀ THAM CHIẾU (RUBRIC 10 TIÊU CHÍ, THANG 1–5) ===

1. Mức độ phù hợp về kỹ năng chuyên môn (Trọng số 0.20 — tiêu chí CỨNG, theo % khớp):
   - Đánh giá mức độ đáp ứng các kỹ năng bắt buộc, ưu tiên và bổ sung theo JD. Đánh giá theo ngữ nghĩa, không chỉ so khớp từ khóa.
   - 5: Đáp ứng ≥95% kỹ năng bắt buộc, có minh chứng dùng thực tế (không có minh chứng thực tế thì tối đa mức 4).
   - 4: Đáp ứng 80–94% kỹ năng bắt buộc.
   - 3: Đáp ứng 60–79% kỹ năng bắt buộc.
   - 2: Đáp ứng 40–59% kỹ năng bắt buộc, thiếu một số kỹ năng quan trọng.
   - 1: Đáp ứng dưới 40% kỹ năng bắt buộc, hoặc hoàn toàn trái ngành.

2. Mức độ phù hợp về kinh nghiệm làm việc (Trọng số 0.20 — tiêu chí CỨNG, theo số năm):
   - Đánh giá số năm kinh nghiệm, vai trò, trách nhiệm, quy mô công việc so với mức JD yêu cầu.
   - 5: Trên 5 năm kinh nghiệm, đúng vai trò/quy mô, mô tả trách nhiệm rõ ràng.
   - 4: Từ 3–5 năm kinh nghiệm, phù hợp phần lớn.
   - 3: Từ 2–3 năm kinh nghiệm liên quan.
   - 2: Từ 1–2 năm kinh nghiệm liên quan.
   - 1: Dưới 1 năm hoặc không có kinh nghiệm liên quan.

3. Trình độ học vấn và chứng chỉ (Trọng số 0.10 — tiêu chí CỨNG, theo bằng cấp):
   - Đánh giá bằng cấp, chuyên ngành, chứng chỉ nghề nghiệp liên quan đến vị trí so với JD.
   - 5: Vượt yêu cầu — Tiến sĩ/Giáo sư đúng chuyên ngành, hoặc chứng chỉ hành nghề cao cấp phù hợp vị trí (VD: CPA cho Kế toán trưởng, PMP cho Quản lý dự án).
   - 4: Thạc sĩ đúng chuyên ngành, hoặc đáp ứng đầy đủ yêu cầu bằng cấp của JD.
   - 3: Đại học đúng chuyên ngành.
   - 2: Đại học trái ngành nhưng có kinh nghiệm thực tế bù đắp (VD: tốt nghiệp Ngôn ngữ Anh nhưng làm Sale 3 năm).
   - 1: Không có bằng cấp hoặc chứng chỉ theo yêu cầu, hoặc bằng cấp không liên quan một chút nào.

4. Mức độ phù hợp về lĩnh vực/ngành nghề (Trọng số 0.10 — tiêu chí CỨNG, theo số năm làm ĐÚNG VAI TRÒ CỤ THỂ):
   - QUAN TRỌNG: chỉ tính số năm làm ĐÚNG vai trò/nghiệp vụ cụ thể mà JD yêu cầu, KHÔNG tính gộp theo ngành lớn.
     Ví dụ: Kế toán tổng hợp và Kế toán thuế cùng khối "Kế toán" nhưng KHÔNG được tính là cùng vai trò.
     Sale công nghệ và Sale bất động sản cùng là "Sale" nhưng KHÔNG được tính là cùng vai trò.
     Không cộng dồn số năm ở vai trò khác cùng ngành vào số năm "đúng vai trò".
   - 5: ≥3 năm làm đúng vai trò cụ thể JD yêu cầu.
   - 4: Từ 2–3 năm làm đúng vai trò cụ thể.
   - 3: Từ 1–2 năm làm đúng vai trò cụ thể.
   - 2: Dưới 1 năm làm đúng vai trò cụ thể; phần lớn kinh nghiệm là vai trò liên quan cùng ngành lớn nhưng khác nghiệp vụ (VD: Kế toán tổng hợp 5 năm ứng tuyển Kế toán thuế; Sale công nghệ 5 năm ứng tuyển Sale bất động sản).
   - 1: Chưa từng làm đúng vai trò, không có kinh nghiệm liên quan cùng ngành (VD: Nhân viên Kho vận ứng tuyển Chuyên viên Marketing).

5. Lộ trình phát triển nghề nghiệp (Trọng số 0.10 — tiêu chí MỀM, theo chiều sâu trách nhiệm):
   - Đánh giá mức độ mở rộng trách nhiệm và phạm vi công việc qua thời gian, KHÔNG bắt buộc phải đổi chức danh hoặc đổi công ty.
     Ứng viên gắn bó lâu ở một công ty/vị trí nhưng được giao thêm việc, quản lý thêm người/ngân sách/khách hàng vẫn được tính là có phát triển.
     LƯU Ý: không được nhầm lẫn hoặc trừ điểm chéo với tiêu chí 9 (Ổn định) — gắn bó lâu một công ty không tự động bị coi là "không phát triển" ở tiêu chí này.
   - 5: Trách nhiệm/phạm vi công việc mở rộng rõ rệt qua từng giai đoạn (VD: từ phụ trách 1 khách hàng lên quản lý cả khu vực; từ nhân viên thành người đào tạo/dẫn dắt đội nhóm dù vẫn giữ nguyên chức danh và công ty).
   - 4: Có mở rộng trách nhiệm ở mức vừa phải (VD: được giao thêm 1–2 đầu việc mới, quản lý thêm ngân sách/khách hàng nhỏ).
   - 3: Duy trì ổn định trách nhiệm, không mở rộng thêm nhưng cũng không thu hẹp.
   - 2: CV không mô tả rõ trách nhiệm có tăng hay không, không đủ căn cứ xác định xu hướng.
   - 1: Trách nhiệm/phạm vi công việc thu hẹp rõ rệt qua thời gian (VD: từ Trưởng nhóm 10 người xuống làm nhân viên không có cấp dưới).

6. Thành tích và tác động đến doanh nghiệp (Trọng số 0.10 — tiêu chí MỀM, theo chất lượng minh chứng):
   - Đánh giá các kết quả mang lại giá trị cho doanh nghiệp, ưu tiên các thành tích có số liệu định lượng.
   - 5: Thành tích nổi bật, có số liệu định lượng rõ (VD: Sale đạt 150% target doanh số quý; Kế toán tối ưu thuế tiết kiệm 2 tỷ/năm).
   - 4: Có thành tích rõ ràng nhưng tác động ở mức vừa (VD: tăng 15% tỷ lệ chốt đơn; giảm 20% lỗi báo cáo tài chính).
   - 3: Có thành tích nhưng thiếu minh chứng cụ thể (VD: "Tham gia dự án tái cấu trúc quy trình bán hàng").
   - 2: Thành tích mơ hồ, không rõ đóng góp cá nhân (VD: "Hỗ trợ team đạt target quý").
   - 1: Chỉ mô tả công việc, không có thành tích (VD: "Thực hiện báo cáo hàng tháng").

7. Minh chứng về kỹ năng mềm (Trọng số 0.05 — tiêu chí MỀM):
   - Đánh giá kỹ năng lãnh đạo, giao tiếp, làm việc nhóm, giải quyết vấn đề qua minh chứng cụ thể trong CV, đối chiếu với level JD yêu cầu.
   - 5: Có nhiều minh chứng hành vi/kết quả cụ thể, ở vai trò dẫn dắt/quản lý (VD: Quản lý đội 15 người, đào tạo nhân viên mới, trình bày báo cáo với Ban Giám đốc).
   - 4: Có minh chứng rõ ràng ở phạm vi nhỏ hơn (VD: Mentor cho nhân viên mới, dẫn dắt nhóm nhỏ 2–3 người).
   - 3: Chỉ liệt kê kỹ năng, không có minh chứng cụ thể (VD: "Kỹ năng giao tiếp tốt").
   - 2: Có đề cập nhưng mơ hồ, thiếu ngữ cảnh (VD: "Từng làm việc nhóm").
   - 1: Không thể hiện kỹ năng mềm trong CV.

8. Khả năng ngoại ngữ và chất lượng trình bày CV (Trọng số 0.05 — tiêu chí CỨNG, theo chứng chỉ/độ chuyên nghiệp):
   - Đánh giá khả năng ngoại ngữ so với JD (nếu JD có yêu cầu) và tính chuyên nghiệp của bố cục, ngữ pháp CV.
   - 5: Chuyên nghiệp, vượt yêu cầu của JD (VD: IELTS ≥7.5, TOEIC ≥900, HSK5+, JLPT N2 trở lên, hoặc thành thạo từ hai ngoại ngữ trở lên).
   - 4: Đạt yêu cầu của JD (VD: IELTS 6.5–7.0, TOEIC 750–899).
   - 3: Có lỗi nhỏ hoặc chứng chỉ ở mức cơ bản (VD: IELTS 5.5–6.0, TOEIC 600–749, hoặc chứng chỉ nội bộ/đã hết hạn nhưng vẫn thể hiện khả năng sử dụng).
   - 2: Có đề cập khả năng ngoại ngữ nhưng không có chứng chỉ minh chứng (VD: "Tiếng Anh giao tiếp"), CV trình bày sơ sài.
   - 1: Không có chứng chỉ ngoại ngữ hoặc không đáp ứng yêu cầu tối thiểu của vị trí; CV khó đọc hoặc nhiều lỗi.

9. Mức độ ổn định và rủi ro nghề nghiệp (Trọng số 0.05 — tiêu chí CỨNG, theo thời gian gắn bó trung bình):
   - Đánh giá mức độ ổn định trong quá trình làm việc và các yếu tố rủi ro cần xác minh (khoảng trống, đổi việc liên tục...).
   - 5: Rất ổn định — trung bình làm 4–5 năm/công ty trở lên, không có khoảng trống bất thường.
   - 4: Có rủi ro nhỏ — trung bình làm 2–3 năm/công ty.
   - 3: Có dấu hiệu cần xác minh — đổi việc mỗi ~12 tháng.
   - 2: Tần suất đổi việc khá cao — đổi việc dưới 12 tháng nhiều lần, có khoảng trống ngắn chưa giải thích.
   - 1: Rủi ro cao — VD: 8 công ty trong 4 năm, nhiều khoảng trống không giải thích.

10. Đánh giá tổng thể bằng AI (Trọng số 0.05 — tiêu chí MỀM, tổng hợp toàn bộ):
   - Phân tích toàn bộ JD và CV để đánh giá mức độ phù hợp, tiềm năng phát triển và đưa ra giải thích minh bạch cho kết quả.
   - 5: Rất phù hợp, đáp ứng ≥95% yêu cầu, có thể đảm nhận công việc ngay với rủi ro thấp.
   - 4: Phù hợp, chỉ thiếu một số kỹ năng có thể đào tạo trong dưới 3 tháng.
   - 3: Có tiềm năng nhưng cần đào tạo 3–6 tháng.
   - 2: Đáp ứng cơ bản, cần đào tạo trên 6 tháng và giám sát chặt.
   - 1: Hoàn toàn trái ngành hoặc thiếu nhiều yêu cầu cốt lõi của vị trí, không phù hợp.

=== CÔNG THỨC QUY CHIẾU TỔNG ĐIỂM (1–5) ===
weighted_total = Σ [ điểm_tiêu_chí_i × trọng_số_i ], với i chạy từ 1 đến 10.
(Trọng số: c1=0.20, c2=0.20, c3=0.10, c4=0.10, c5=0.10, c6=0.10, c7=0.05, c8=0.05, c9=0.05, c10=0.05 — tổng trọng số = 1.0)
Mốc tham chiếu tổng điểm (1–5):
   - 4.5-5.0: Xuất sắc, khớp gần như toàn bộ JD, có số liệu/thành tích nổi bật, đúng vai trò, ít rủi ro.
   - 4.0-4.4: Rất phù hợp nhưng vẫn thiếu một vài minh chứng hoặc kỹ năng phụ.
   - 3.5-3.9: Phù hợp để phỏng vấn, còn gap rõ cần xác minh.
   - 3.0-3.4: Có tiềm năng nhưng thiếu nhiều điểm quan trọng.
   - 2.0-2.9: Yếu hoặc lệch đáng kể so với JD.
   - <2.0: Không phù hợp.

=== HƯỚNG DẪN OUTPUT JSON ===
Chỉ trả về JSON thuần (KHÔNG markdown ```json, KHÔNG văn bản thừa):
{{
  "criteria_scores": {{
    "c1_technical_skills": <số nguyên 1-5>,
    "c2_experience": <số nguyên 1-5>,
    "c3_education": <số nguyên 1-5>,
    "c4_industry": <số nguyên 1-5>,
    "c5_career_path": <số nguyên 1-5>,
    "c6_achievements": <số nguyên 1-5>,
    "c7_soft_skills": <số nguyên 1-5>,
    "c8_language_cv": <số nguyên 1-5>,
    "c9_stability": <số nguyên 1-5>,
    "c10_ai_overall": <số nguyên 1-5>
  }},
  "weighted_total": <số thực 1-5, tính theo công thức quy chiếu ở trên>,
  "reasons": {{
    "c1_technical_skills": "<Liệt kê kỹ năng ứng viên có. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [thiếu kỹ năng gì theo JD / lý do trừ điểm]'>",
    "c2_experience": "<Nêu số năm kinh nghiệm. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [thiếu sót gì so với JD / lý do trừ]'>",
    "c3_education": "<Trích dẫn bằng cấp. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [chưa đạt yêu cầu vượt trội / lý do trừ]'>",
    "c4_industry": "<Nêu rõ số năm làm ĐÚNG vai trò cụ thể (không gộp ngành lớn). NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [chênh lệch vai trò/nghiệp vụ thế nào]'>",
    "c5_career_path": "<Nêu minh chứng mở rộng trách nhiệm/phạm vi công việc. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [lý do trừ]'>",
    "c6_achievements": "<Nêu số liệu thành tích. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [thiếu mức độ thành tích theo yêu cầu]'>",
    "c7_soft_skills": "<Trích dẫn hành động. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [thiếu minh chứng cho kỹ năng mềm nào]'>",
    "c8_language_cv": "<Nhận xét CV & ngoại ngữ. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [lỗi form / ngoại ngữ kém]'>",
    "c9_stability": "<Nêu trung bình năm/công ty. NẾU điểm < 5, BẮT BUỘC thêm 'Điểm trừ: [rủi ro nhảy việc]'>",
    "c10_ai_overall": "<Kết luận tổng quát lý do điểm tổng. Chỉ ra Điểm mạnh nhất và Điểm rủi ro nhất.>"
  }},
  "evidence": {{
    "matched_requirements": ["Yêu cầu JD đã khớp + bằng chứng ngắn trong CV"],
    "missing_requirements": ["Yêu cầu JD còn thiếu/không thấy trong CV"],
    "transferable_strengths": ["Điểm mạnh có thể chuyển đổi sang vị trí này"],
    "quantified_achievements": ["Thành tích có số liệu; nếu không có thì trả []"]
  }},
  "risk_flags": [
    {{"risk": "rủi ro hoặc nghi vấn", "severity": "low|medium|high", "why": "vì sao cần lưu ý"}}
  ],
  "interview_focus": [
    {{"topic": "nội dung cần hỏi kỹ", "question": "câu hỏi phỏng vấn đề xuất", "why": "lý do cần xác minh"}}
  ],
  "confidence": {{
    "level": "low|medium|high",
    "reason": "mức độ chắc chắn dựa trên độ đầy đủ của CV/JD"
  }},
  "summary": "<Tóm tắt 80-100 từ tiếng Việt: 2 điểm mạnh nổi trội và 2 điểm yếu/điểm rủi ro cần làm rõ trong phỏng vấn>"
}}"""

EVAL_PROMPT = """Bạn là chuyên gia đánh giá phỏng vấn tuyển dụng nghiêm khắc, ưu tiên bằng chứng thực tế hơn lời kể chung chung.

Vị trí ứng tuyển: {position}
Loại câu hỏi: {q_type} (Câu {q_num}/8)
Câu hỏi: {question}

Câu trả lời của ứng viên (chuyển từ giọng nói):
\"\"\"{transcript}\"\"\"

Nguyên tắc chấm khắt khe:
- Không cộng điểm vì ứng viên nói dài; chỉ chấm cao khi có bằng chứng hành động, vai trò cá nhân, quy trình/công cụ, kết quả và bài học/kiểm soát rủi ro.
- Phân biệt rõ "tôi trực tiếp làm" với "đội/công ty làm"; nếu vai trò cá nhân mơ hồ thì không được xếp nắm vững.
- Với câu chuyên môn, phải soi các khía cạnh: bối cảnh nghiệp vụ, phương pháp xử lý, dữ liệu/chỉ số, công cụ/hệ thống, phối hợp liên phòng ban, kết quả định lượng, rủi ro/sai sót và cách kiểm soát.
- Với câu kinh nghiệm, phải soi: quy mô công việc, trách nhiệm trực tiếp, độ phức tạp, thành tựu đo được, thất bại/khó khăn và mức độ tương đồng với vị trí ứng tuyển.
- Thiếu số liệu/kết quả cụ thể thì tối đa "am hiểu"; thiếu ví dụ thực tế thì tối đa "có biết qua"; trả lời lệch câu hỏi hoặc chỉ nói khẩu hiệu thì "không biết".
- Chỉ xếp "nắm vững" khi câu trả lời có tình huống cụ thể, hành động rõ của ứng viên, lý do lựa chọn cách làm, kết quả/impact có thể kiểm chứng và thể hiện hiểu sâu.

Đánh giá theo đúng 4 mức sau (chọn 1):
- nắm vững   : Có case cụ thể, vai trò cá nhân rõ, phương pháp/chỉ số/công cụ rõ, kết quả hoặc tác động đo được, xử lý được rủi ro/ngoại lệ.
- am hiểu    : Đúng trọng tâm và có ví dụ/hướng xử lý, nhưng còn thiếu một phần quan trọng như số liệu, kết quả, công cụ, hoặc vai trò cá nhân chưa thật rõ.
- có biết qua: Nắm khái niệm hoặc kể trải nghiệm bề mặt, thiếu quy trình cụ thể, thiếu minh chứng, thiếu phân tích nguyên nhân-kết quả.
- không biết : Không trả lời, trả lời sai/lệch trọng tâm, quá chung chung, hoặc không chứng minh được năng lực liên quan.

Trả về JSON (không markdown):
{{
  "level": "nắm vững" | "am hiểu" | "có biết qua" | "không biết",
  "feedback": "Nhận xét 2-4 câu bằng tiếng Việt, nêu rõ bằng chứng nào đạt/chưa đạt và vì sao xếp mức này; phải khắt khe, không khen chung chung",
  "strengths": "Điểm mạnh có bằng chứng trong câu trả lời; nếu không có bằng chứng thì để trống",
  "improvements": "Các điểm cần hỏi/kiểm chứng thêm: số liệu, kết quả, vai trò cá nhân, công cụ, rủi ro hoặc tình huống cụ thể còn thiếu",
  "normalized_transcript": "Viết lại câu trả lời rõ ràng trong tối đa 900 ký tự dựa trên ngữ cảnh câu hỏi '{question}': giữ nguyên ý chính của ứng viên, sửa lỗi STT/chính tả, bỏ từ à/ừm/thì/là/mà dư thừa, giữ đúng thuật ngữ chuyên ngành liên quan đến chủ đề đang hỏi"
}}"""

SOFT_SKILL_EVAL_PROMPT = """Bạn là chuyên gia đánh giá kỹ năng mềm trong tuyển dụng, chấm nhận xét theo hướng nghiêm khắc và dựa trên bằng chứng hành vi.

Câu hỏi phỏng vấn: {question}

Câu trả lời của ứng viên (chuyển từ giọng nói):
\"\"\"{transcript}\"\"\"

Phân tích định tính câu trả lời — KHÔNG xếp mức, KHÔNG cho điểm số.
Đánh giá khắt khe về: tình huống cụ thể, hành động cá nhân, kết quả, trách nhiệm nhận về mình, cách xử lý mâu thuẫn/áp lực, khả năng tự nhận thức, bài học và mức độ phù hợp văn hóa. Nếu thiếu STAR hoặc thiếu kết quả đo được, phải nêu rõ.

Trả về JSON (không markdown):
{{
  "feedback": "Nhận xét tổng quan 3-4 câu bằng tiếng Việt, chỉ rõ bằng chứng hành vi nào đủ/chưa đủ",
  "strengths": "Điểm mạnh nổi bật có bằng chứng trong câu trả lời (để trống nếu không có)",
  "improvements": "Gợi ý khai thác thêm cụ thể: tình huống, hành động cá nhân, kết quả, bài học hoặc rủi ro còn thiếu",
  "normalized_transcript": "Viết lại câu trả lời rõ ràng trong tối đa 900 ký tự dựa trên ngữ cảnh câu hỏi '{question}': giữ nguyên ý chính của ứng viên, sửa lỗi STT/chính tả, bỏ từ à/ừm/thì/là/mà dư thừa, thêm dấu câu phù hợp, diễn đạt tự nhiên như người đang kể chuyện/trả lời phỏng vấn"
}}"""

CV_QUESTIONS_PROMPT = """Bạn là HR Interviewer đang chuẩn bị phỏng vấn cho vị trí {position} (cấp bậc: {level}).

MỤC TIÊU BẮT BUỘC: Tạo câu hỏi phỏng vấn dựa trên JD là chính. CV chỉ là nguồn phụ để cá nhân hóa câu hỏi, chọn bằng chứng cần xác minh, kiểm tra khoảng trống, hoặc đào sâu kinh nghiệm có liên quan trực tiếp đến JD.

Mô tả công việc (JD) - nguồn ưu tiên:
{jd_text}

CV của ứng viên - nguồn đối chiếu:
{cv_text}

Tạo đúng {num_gen} câu hỏi phỏng vấn để kiểm tra mức độ phù hợp với JD.
Yêu cầu:
- Ưu tiên 100% các năng lực, trách nhiệm, công cụ, nghiệp vụ và tiêu chí bắt buộc/nổi bật trong JD.
- Chỉ hỏi về thông tin trong CV nếu thông tin đó LIÊN QUAN trực tiếp đến JD hoặc giúp xác minh khoảng cách so với JD.
- Nếu CV có kinh nghiệm/kỹ năng không liên quan JD, BẮT BUỘC bỏ qua; không tạo câu hỏi chỉ vì CV có nhắc tới.
- Nếu CV lệch vai trò/ngành so với JD (ví dụ JD Tuyển dụng nhưng CV chủ yếu Tech/Developer), KHÔNG hỏi sâu chuyên môn cũ như coding, framework, system design. Thay vào đó hỏi về khả năng chuyển đổi sang yêu cầu JD, kinh nghiệm có thể chuyển giao, hiểu biết về nghiệp vụ JD, và kế hoạch bù đắp gap.
- Nếu CV thiếu minh chứng cho yêu cầu quan trọng trong JD, hãy hỏi để ứng viên chứng minh năng lực hoặc làm rõ khoảng trống.
- Mỗi câu BẮT BUỘC gắn với một yêu cầu JD rõ ràng: kỹ năng chuyên môn, trách nhiệm chính, kinh nghiệm thực tế, quy mô công việc, công cụ/hệ thống, chỉ số/kết quả, rủi ro/kiểm soát.
- Không hỏi về công ty/dự án/kỹ năng trong CV nếu không nêu được vì sao nó liên quan tới yêu cầu JD.
- Nếu dùng cụm "Trong CV bạn có đề cập...", cùng câu đó phải nối rõ với yêu cầu JD, ví dụ "JD yêu cầu X, trong CV bạn có đề cập Y liên quan đến X...".
- Tuyệt đối không tạo câu hỏi dạng "Bạn đã dùng công nghệ/công cụ/kỹ thuật X trong CV như thế nào?" nếu X không phải yêu cầu hoặc năng lực chuyển giao trực tiếp trong JD.
- Câu hỏi hợp lệ phải trả lời được câu: "Câu này giúp đánh giá yêu cầu nào trong JD?" Nếu không trả lời được, câu hỏi đó không hợp lệ.
- Điều chỉnh độ khó/chiều sâu phù hợp với cấp bậc {level} (Entry=cơ bản, Mid=dự án thực tế, Senior/Manager=lãnh đạo/chiến lược)
- Hỏi cụ thể, không hỏi chung chung; ưu tiên yêu cầu ứng viên nêu ví dụ, vai trò cá nhân, số liệu/kết quả, công cụ và cách xử lý rủi ro.
- Có thể bắt đầu bằng: "JD yêu cầu...", "Vị trí này cần...", "Trong CV bạn có đề cập...", "Bạn có thể chứng minh kinh nghiệm..." hoặc tương tự.
- Viết bằng tiếng Việt, ngắn gọn (1-2 câu mỗi câu hỏi)
- Trước khi trả JSON, tự kiểm tra từng câu: nếu câu nào không truy ra được một yêu cầu trong JD thì viết lại câu đó.

Trả về JSON (không markdown):
{json_format}"""

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
    "q07": "Dựa trên yêu cầu quan trọng nhất của JD, hãy mô tả kinh nghiệm liên quan nhất của bạn. Nếu CV hiện chưa có kinh nghiệm đúng vai trò, hãy nêu năng lực có thể chuyển giao và kế hoạch bù đắp khoảng trống.",
    "q08": "JD của vị trí này yêu cầu xử lý các tình huống thực tế trong đúng nghiệp vụ ứng tuyển. Bạn hãy nêu một tình huống liên quan trực tiếp; nếu chưa từng làm, hãy trình bày cách bạn sẽ tiếp cận và học để đáp ứng yêu cầu."
}

LEVEL_ORDER = {"nắm vững": 10, "am hiểu": 7.5, "có biết qua": 5, "không biết": 0}

_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

THIRD_PARTY_WEBHOOK_URL = os.environ.get("THIRD_PARTY_WEBHOOK_URL", "")
THIRD_PARTY_WEBHOOK_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("THIRD_PARTY_WEBHOOK_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}

DEEP_ANALYSIS_PROMPT = """Bạn là một Chuyên gia Tuyển dụng cấp cao. 
Nhiệm vụ của bạn là phân tích sâu CV của ứng viên đối chiếu với Mô tả công việc (JD), sau đó sinh ra một số câu hỏi phỏng vấn chuyên sâu (deep analysis) phù hợp với các điểm cần xác minh thực tế.

YÊU CẦU CHO CÁC CÂU HỎI:
1. Phải dựa hoàn toàn vào các dự án, kỹ năng, kinh nghiệm CỤ THỂ mà ứng viên đã ghi trong CV.
2. Phải xoáy sâu vào chuyên môn, cách giải quyết vấn đề, khó khăn vướng mắc thực tế ứng viên đã trải qua.
3. Liên kết chặt chẽ với các yêu cầu cốt lõi của JD.
4. Tránh tuyệt đối các câu hỏi chung chung (ví dụ: "Bạn hãy giới thiệu bản thân", "Điểm mạnh của bạn là gì?").
5. Tuỳ vào độ phong phú của CV và mức độ rủi ro so với JD mà tạo số lượng câu hỏi cho hợp lý. Không cố định số lượng; chỉ hỏi các điểm thật sự cần xác minh. Thông thường 1-5 câu, trường hợp CV/JD phức tạp có thể tối đa 8 câu.

CV Ứng Viên:
{cv_text}

Mô tả công việc (JD):
{jd_text}

HÃY XUẤT RA DANH SÁCH CÁC CÂU HỎI THEO ĐÚNG ĐỊNH DẠNG JSON MẢNG (Array of strings). Không kèm giải thích.
Ví dụ:
[
  "Câu hỏi 1",
  "Câu hỏi 2"
]
"""

EVALUATE_REPLY_PROMPT = """Bạn là Chuyên gia Tuyển dụng cấp cao. 
Nhiệm vụ của bạn là đánh giá câu trả lời của ứng viên cho các câu hỏi chuyên sâu (Deep Analysis) đã được gửi qua email.

YÊU CẦU:
1. Đối chiếu câu trả lời của ứng viên với CV của họ và yêu cầu của JD.
2. Đánh giá tính chân thực, mức độ hiểu biết chuyên môn, và khả năng giải quyết vấn đề.
3. Chỉ ra những điểm mạnh (red flags nếu có) từ câu trả lời.
4. Đưa ra kết luận: Câu trả lời có đáp ứng được kỳ vọng để mời phỏng vấn chính thức hay không.
5. Chấm điểm cộng/trừ: Dựa vào chất lượng câu trả lời, hãy cho một mức điểm cộng/trừ nhỏ (từ -1.0 đến +1.0) để cộng/trừ vào điểm đánh giá CV gốc. Trả lời tốt, logic thì cộng. Trả lời kém, lan man thì trừ. Luôn nêu rõ lý do vì sao cộng/trừ/giữ nguyên điểm.

Câu hỏi Deep Analysis đã gửi:
{deep_questions}

Câu trả lời của Ứng viên (qua Email):
{candidate_reply}

CV Ứng Viên:
{cv_text}

Mô tả công việc (JD):
{jd_text}

HÃY XUẤT RA KẾT QUẢ ĐÁNH GIÁ DƯỚI DẠNG JSON với các trường:
- "evaluation": Đánh giá chi tiết (string).
- "red_flags": Các điểm đáng ngờ hoặc yếu kém (array of strings).
- "strengths": Các điểm mạnh thể hiện qua câu trả lời (array of strings).
- "recommendation": "Phê duyệt" hoặc "Từ chối" (string).
- "score_adjustment": Số điểm cộng/trừ (kiểu số float, ví dụ: 0.5 hoặc -0.2).
- "score_adjustment_reason": Lý do cụ thể vì sao cộng/trừ/giữ nguyên điểm (string).
"""

CV_EVAL_ROUND_1_PROMPT = """Bạn là hệ thống AI PAI Engine đóng vai trò Chuyên gia Tuyển dụng.
Nhiệm vụ của bạn là kiểm tra xem CV của ứng viên có đủ thông tin để đánh giá theo Tiêu chí (Criteria) và JD hay không.
Nếu thông tin trong CV bị thiếu, không rõ ràng so với các yêu cầu quan trọng, hãy đặt câu hỏi để yêu cầu ứng viên bổ sung.
Nếu thông tin đã đầy đủ, hãy tiến hành chấm điểm (thang điểm 10).

=== MÔ TẢ CÔNG VIỆC (JD) ===
{jd_text}

=== TIÊU CHÍ ĐÁNH GIÁ (CRITERIA) ===
{criteria_text}

=== CV ỨNG VIÊN ===
{cv_text}

CHỈ TRẢ VỀ KẾT QUẢ ĐỊNH DẠNG JSON THEO 1 TRONG 2 TRƯỜNG HỢP SAU:

Trường hợp 1: Thiếu thông tin (Cần hỏi thêm)
{{
  "status": "NEED_INFO",
  "questions": [
    "Câu hỏi 1 để làm rõ...",
    "Câu hỏi 2 để làm rõ..."
  ]
}}

Trường hợp 2: Đủ thông tin (Hoàn thành đánh giá)
{{
  "status": "COMPLETED",
  "result": "PASS", // hoặc "FAIL"
  "score": 8.5, // Điểm từ 0 đến 10
  "rationale": "Lý do chi tiết cho điểm số và quyết định dựa trên tiêu chí..."
}}
"""

CV_EVAL_ROUND_2_PROMPT = """Bạn là hệ thống AI PAI Engine đóng vai trò Chuyên gia Tuyển dụng.
Đây là vòng đánh giá CUỐI CÙNG. Bạn phải đưa ra quyết định đánh giá dựa trên CV, JD, Tiêu chí và các CÂU TRẢ LỜI bổ sung của ứng viên.

=== MÔ TẢ CÔNG VIỆC (JD) ===
{jd_text}

=== TIÊU CHÍ ĐÁNH GIÁ (CRITERIA) ===
{criteria_text}

=== CV ỨNG VIÊN ===
{cv_text}

=== CÂU TRẢ LỜI BỔ SUNG CỦA ỨNG VIÊN ===
{answers_text}

YÊU CẦU:
Dựa vào tất cả thông tin trên, hãy chấm điểm ứng viên (thang điểm 10) và đưa ra quyết định (PASS/FAIL).
Bạn KHÔNG được yêu cầu thêm thông tin. Đây là bước bắt buộc phải ra kết quả.

CHỈ TRẢ VỀ KẾT QUẢ ĐỊNH DẠNG JSON SAU:
{{
  "status": "COMPLETED",
  "result": "PASS", // hoặc "FAIL"
  "score": 8.5, // Điểm từ 0 đến 10
  "rationale": "Lý do chi tiết cho điểm số và quyết định dựa trên CV và các câu trả lời bổ sung..."
}}
"""
