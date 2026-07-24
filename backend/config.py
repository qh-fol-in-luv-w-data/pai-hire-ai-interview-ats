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
PASS_SCORE      = 6.0
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
    "04": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_B", "is_dynamic": True, "text": "Trong CV, anh/chị có đề cập kỹ năng [kỹ năng trong CV]. Anh/chị mô tả cụ thể mức độ và tần suất sử dụng kỹ năng này trong công việc gần đây nhất." },
    "05": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_C", "is_dynamic": True, "text": "Nếu không có sẵn công cụ/tài nguyên quen thuộc, anh/chị sẽ vận dụng kỹ năng [kỹ năng JD] như thế nào để vẫn hoàn thành công việc đúng chất lượng?" },
    "06": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_C", "is_dynamic": False, "text": "Anh/chị có thể nêu một chỉ số hoặc kết quả cụ thể để chứng minh mức độ thành thạo kỹ năng vừa chia sẻ không?" },
    "07": { "type": "Technical", "label": "Tiêu chí 01", "group": "Nhóm_D", "is_dynamic": False, "text": "Đưa 1 bài tập/tình huống chuyên môn thực tế đang xảy ra tại phòng ban, yêu cầu ứng viên nêu hướng xử lý ngắn gọn để xác nhận mức độ thành thạo kỹ năng thực tế." },
    "08": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hãy giới thiệu ngắn gọn về quá trình làm việc, vai trò và trách nhiệm chính qua từng vị trí đã đảm nhận." },
    "09": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_B", "is_dynamic": True, "text": "Dựa trên CV, anh/chị có kinh nghiệm [số năm] năm ở vị trí [chức danh]. Anh/chị mô tả cụ thể quy mô công việc, số lượng dự án/nhân sự phụ trách và mức độ tương đồng với vị trí đang ứng tuyển." },
    "10": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_B", "is_dynamic": False, "text": "Nếu được nhận vào vị trí này, trong 2 tuần đầu tiên anh/chị sẽ ưu tiên tìm hiểu và triển khai những việc gì để bắt nhịp công việc dựa trên kinh nghiệm đã có?" },
    "11": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_C", "is_dynamic": True, "text": "Trong quá trình thực hiện [công việc/dự án trong CV], đâu là khó khăn lớn nhất về mặt kinh nghiệm/năng lực và anh/chị đã xử lý như thế nào?" },
    "12": { "type": "Experience", "label": "Tiêu chí 02", "group": "Nhóm_C", "is_dynamic": True, "text": "Một số kinh nghiệm của anh/chị đang nghiêng về [mảng A], trong khi vị trí này yêu cầu nhiều về [mảng B]. Anh/chị đánh giá khoảng cách này như thế nào và sẽ bù đắp ra sao?" },
    "13": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị hãy chia sẻ về chuyên ngành đào tạo và các chứng chỉ nghề nghiệp liên quan trực tiếp đến vị trí đang ứng tuyển." },
    "14": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_B", "is_dynamic": True, "text": "CV thể hiện anh/chị tốt nghiệp [chuyên ngành/trường]. Anh/chị đã áp dụng kiến thức được đào tạo vào công việc thực tế như thế nào?" },
    "15": { "type": "General", "label": "Tiêu chí 03", "group": "Nhóm_C", "is_dynamic": False, "text": "Nếu chuyên ngành đào tạo của anh/chị không hoàn toàn trùng khớp với yêu cầu JD, anh/chị đã bổ sung kiến thức/chứng chỉ liên quan bằng cách nào để đáp ứng công việc?" },
    "16": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_A", "is_dynamic": True, "text": "Anh/chị đã có kinh nghiệm làm việc trong ngành [ngành nghề theo JD] chưa? Nếu chưa, anh/chị đánh giá ngành mình từng làm có điểm gì tương đồng với ngành này?" },
    "17": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_B", "is_dynamic": True, "text": "CV cho thấy anh/chị chủ yếu làm việc trong lĩnh vực [ngành trong CV], trong khi vị trí này thuộc lĩnh vực [ngành JD]. Anh/chị dự kiến sẽ thích nghi với sự khác biệt này như thế nào?" },
    "18": { "type": "Experience", "label": "Tiêu chí 04", "group": "Nhóm_C", "is_dynamic": True, "text": "Nếu gặp một vấn đề đặc thù của ngành [ngành JD] mà anh/chị chưa từng xử lý trước đây, anh/chị sẽ tiếp cận và tìm hiểu theo phương pháp nào?" },
    "19": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": False, "text": "Anh/chị mong muốn phát triển năng lực gì trong 6 -12 tháng tới nếu gia nhập CT Group? Anh/chị sẽ đo lường sự tiến bộ đó như thế nào?" },
    "20": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": True, "text": "Dựa trên CV, anh/chị đã trải qua các vị trí [liệt kê chức danh theo thời gian]. Anh/chị mô tả sự thay đổi về trách nhiệm và quy mô công việc qua từng giai đoạn này." },
    "21": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_A", "is_dynamic": True, "text": "Điều gì đã thúc đẩy anh/chị chuyển từ vị trí [vị trí trước] sang [vị trí sau]? Đây có phải là một bước phát triển theo đúng định hướng anh/chị đặt ra không?" },
    "22": { "type": "General", "label": "Tiêu chí 05", "group": "Nhóm_C", "is_dynamic": True, "text": "Trong CV có giai đoạn [khoảng thời gian ít thay đổi chức danh/vai trò]. Anh/chị có thể chia sẻ rõ hơn lý do và những gì đã tích lũy được trong giai đoạn đó không?" },
    "23": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_A", "is_dynamic": False, "text": "Hãy chia sẻ một thành tích hoặc dự án/công việc mà anh/chị tự đánh giá là nổi bật nhất trong thời gian gần đây. Vai trò cụ thể của anh/chị trong kết quả đó là gì?" },
    "24": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_B", "is_dynamic": True, "text": "Kết quả [thành tích/chỉ số trong CV] được đo lường như thế nào? Anh/chị trực tiếp đóng góp phần nào trong kết quả này?" },
    "25": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_B", "is_dynamic": False, "text": "Hãy chia sẻ một kết quả cụ thể mà anh/chị đạt được vượt hơn yêu cầu ban đầu, được đo lường bằng chỉ số, dữ liệu hoặc phản hồi cụ thể." },
    "26": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_C", "is_dynamic": True, "text": "Anh/chị vừa đề cập thành tích [thành tích]. Anh/chị có thể nêu một chỉ số cụ thể (số liệu, %, mốc thời gian) để chứng minh kết quả này không?" },
    "27": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_C", "is_dynamic": False, "text": "Trong thành tích đó, phần việc nào do anh/chị trực tiếp phụ trách, phần nào do đội nhóm hỗ trợ?" },
    "28": { "type": "Experience", "label": "Tiêu chí 06", "group": "Nhóm_D", "is_dynamic": True, "text": "AI đang ghi nhận thành tích [thành tích ứng viên nêu] nhưng chưa đủ minh chứng định lượng. Đề nghị HOD hỏi thêm để xác nhận mức độ đóng góp thực tế và độ tin cậy của số liệu." },
    "29": { "type": "Soft Skill", "label": "Tiêu chí 07", "group": "Nhóm_A", "is_dynamic": False, "text": "Trong môi trường làm việc tốc độ cao, nhiều yêu cầu thay đổi nhanh, anh/chị thường quản lý công việc, deadline và áp lực như thế nào?" },
    "30": { "type": "Soft Skill", "label": "Tiêu chí 07", "group": "Nhóm_B", "is_dynamic": True, "text": "CV có đề cập anh/chị từng [dẫn dắt đội nhóm/đào tạo nhân sự/thuyết trình]. Anh/chị hãy chia sẻ một tình huống cụ thể thể hiện kỹ năng này và kết quả đạt được." },
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
Nhiệm vụ của bạn là đánh giá CV của ứng viên so với Mô tả công việc (JD), cho điểm CHÍNH XÁC theo 10 tiêu chí dưới đây (Tổng tối đa 10 điểm).

QUY TẮC CHẤM ĐIỂM (CỰC KỲ QUAN TRỌNG):
1. Chấm theo hướng TUYỂN DỤNG THẬN TRỌNG. Điểm 9.0+ là trường hợp hiếm, chỉ dành cho CV gần như khớp JD, có thành tích định lượng mạnh và có thể làm ngay.
2. Không suy diễn tốt cho ứng viên. Chỉ cho điểm dựa trên bằng chứng xuất hiện trong CV/JD. Nếu CV không nêu rõ một kỹ năng/kinh nghiệm/thành tích, xem là thiếu minh chứng.
3. Mốc tham chiếu tổng điểm:
   - 9.0-10.0: Xuất sắc, khớp gần như toàn bộ JD, có số liệu/thành tích nổi bật, cùng ngành, ít rủi ro.
   - 8.0-8.9: Rất phù hợp nhưng vẫn thiếu một vài minh chứng hoặc kỹ năng phụ.
   - 7.0-7.9: Phù hợp để phỏng vấn, còn gap rõ cần xác minh.
   - 6.0-6.9: Có tiềm năng nhưng thiếu nhiều điểm quan trọng.
   - 4.0-5.9: Yếu hoặc lệch đáng kể so với JD.
   - <4.0: Không phù hợp.
4. Nếu một tiêu chí thiếu minh chứng rõ ràng, không được cho điểm ở nhóm cao nhất của tiêu chí đó.
5. Trong `reasons`, luôn ghi rõ bằng chứng đã dùng và điểm trừ/rủi ro chính. Không được viết chung chung kiểu "phù hợp tốt" nếu thiếu dẫn chứng.

=== JOB DESCRIPTION ===
{jd}

=== CV ỨNG VIÊN ===
{cv}

=== KHUNG ĐÁNH GIÁ VÀ THAM CHIẾU (RUBRIC 10 TIÊU CHÍ) ===

1. Mức độ phù hợp về kỹ năng chuyên môn (Tối đa 2.0đ):
   - Đánh giá mức độ đáp ứng các kỹ năng bắt buộc, ưu tiên và bổ sung theo JD. Đánh giá theo ngữ nghĩa.
   - 1.8-2.0đ: Đáp ứng ≥95% kỹ năng bắt buộc, có minh chứng dùng thực tế. Không có minh chứng thực tế thì tối đa 1.6.
   - 1.5-1.75đ: Đáp ứng 80–94%.
   - 1.2-1.4đ: Đáp ứng 60–79%.
   - 0.5-1.1đ: Thiếu rất nhiều kỹ năng quan trọng.
   - 0.0đ: HOÀN TOÀN KHÔNG CÓ KỸ NĂNG LIÊN QUAN (trái ngành 100%).

2. Mức độ phù hợp về kinh nghiệm làm việc (Tối đa 2.0đ):
   - Đánh giá số năm kinh nghiệm, vai trò, trách nhiệm so với mức yêu cầu của JD.
   - 1.8-2.0đ: Kinh nghiệm rất phù hợp, đúng vai trò/quy mô, đạt hoặc vượt mốc JD và có mô tả trách nhiệm rõ.
   - 1.5-1.75đ: Phù hợp phần lớn.
   - 1.2-1.4đ: Có kinh nghiệm liên quan.
   - 0.5-1.1đ: Thiếu đáng kể.
   - 0.0đ: TRÁI NGÀNH HOÀN TOÀN, không có chút kinh nghiệm nào dính líu tới JD.

3. Trình độ học vấn và chứng chỉ (Tối đa 1.0đ):
   - Đánh giá bằng cấp, chuyên ngành, chứng chỉ nghề nghiệp liên quan đến vị trí so với JD.
   - 1.0đ: Vượt yêu cầu.
   - 0.8-0.9đ: Đáp ứng đầy đủ nhưng chưa vượt yêu cầu.
   - 0.6-0.7đ: Đáp ứng một phần (ví dụ bằng cấp liên quan nhưng không đúng chuyên ngành).
   - 0.1-0.5đ: Không đáp ứng đủ.
   - 0.0đ: Không có bằng cấp hoặc bằng cấp không liên quan một chút nào.

4. Mức độ phù hợp về lĩnh vực/ngành nghề (Tối đa 1.0đ):
   - Đánh giá kinh nghiệm làm việc trong cùng lĩnh vực hoặc có mức tương đồng cao.
   - 0.9-1.0đ: Cùng ngành/lĩnh vực trực tiếp với JD và có kinh nghiệm gần đây.
   - 0.75-0.85đ: Ngành tương tự.
   - 0.6-0.7đ: Có thể chuyển đổi.
   - 0.0-0.5đ: KHÁC BIỆT HOÀN TOÀN (VD: JD IT nhưng CV là Nhân sự -> BẮT BUỘC 0.0).

5. Lộ trình phát triển nghề nghiệp (Tối đa 1.0đ):
   - Đánh giá sự phát triển về chức danh, trách nhiệm hoặc chiều sâu chuyên môn.
   - 0.9-1.0đ: Phát triển rõ ràng về chức danh/trách nhiệm/quy mô, có bằng chứng cụ thể.
   - 0.75-0.85đ: Phát triển ổn định.
   - 0.6-0.7đ: Ít thay đổi.
   - 0.0-0.5đ: Không phát triển, hoặc trái ngành hoàn toàn nên lộ trình vô nghĩa.

6. Thành tích và tác động đến doanh nghiệp (Tối đa 1.0đ):
   - Đánh giá các kết quả mang lại giá trị, ưu tiên các thành tích có số liệu định lượng.
   - 0.9-1.0đ: Thành tích nổi bật, có số liệu định lượng hoặc tác động kinh doanh rõ.
   - 0.75-0.85đ: Có thành tích rõ ràng.
   - 0.6-0.7đ: Có thành tích nhưng thiếu minh chứng định lượng.
   - 0.0-0.5đ: Chỉ mô tả công việc hoặc thành tích trái ngành không áp dụng được.

7. Minh chứng về kỹ năng mềm (Tối đa 0.5đ):
   - Đánh giá kỹ năng mềm (lãnh đạo, làm việc nhóm, giao tiếp) qua minh chứng trong CV dựa trên level của JD.
   - 0.45-0.5đ: Có nhiều minh chứng hành vi/kết quả cụ thể.
   - 0.35-0.4đ: Có minh chứng rõ ràng.
   - 0.1-0.3đ: Chỉ liệt kê kỹ năng.
   - 0.0đ: Không thể hiện.

8. Khả năng ngoại ngữ và trình bày CV (Tối đa 0.5đ):
   - Đánh giá ngoại ngữ (so với JD) và tính chuyên nghiệp của bố cục CV.
   - 0.45-0.5đ: CV trình bày chuyên nghiệp và đáp ứng/vượt yêu cầu ngoại ngữ nếu JD có yêu cầu.
   - 0.35-0.4đ: Đạt yêu cầu.
   - 0.1-0.3đ: Có lỗi nhỏ.
   - 0.0đ: Khó đọc hoặc sai nhiều lỗi.

9. Mức độ ổn định và rủi ro nghề nghiệp (Tối đa 0.5đ):
   - Đánh giá mức độ ổn định trong quá trình làm việc.
   - 0.45-0.5đ: Rất ổn định, không có khoảng trống/chuyển việc bất thường cần xác minh.
   - 0.35-0.4đ: Có rủi ro nhỏ.
   - 0.1-0.3đ: Có dấu hiệu cần xác minh.
   - 0.0đ: Rủi ro quá cao.

10. Đánh giá tổng thể bằng AI (Tối đa 0.5đ):
   - Phân tích toàn bộ JD và CV để đánh giá mức độ phù hợp.
   - 0.45-0.5đ: Rất phù hợp, đáp ứng ≥95%, có thể làm ngay với rủi ro thấp.
   - 0.35-0.4đ: Phù hợp, thiếu 1 số kỹ năng nhưng đào tạo được.
   - 0.1-0.3đ: Tiềm năng, cần đào tạo lâu.
   - 0.0đ: HOÀN TOÀN TRÁI NGÀNH, KHÔNG THỂ NHẬN. BỘ HỒ SƠ NÀY CHỈ XỨNG ĐÁNG DƯỚI 2/10 ĐIỂM.

=== HƯỚNG DẪN OUTPUT JSON ===
Chỉ trả về JSON thuần (KHÔNG markdown ```json, KHÔNG văn bản thừa):
{{
  "criteria_scores": {{
    "c1_technical_skills": <điểm từ 0 đến 2.0>,
    "c2_experience": <điểm từ 0 đến 2.0>,
    "c3_education": <điểm từ 0 đến 1.0>,
    "c4_industry": <điểm từ 0 đến 1.0>,
    "c5_career_path": <điểm từ 0 đến 1.0>,
    "c6_achievements": <điểm từ 0 đến 1.0>,
    "c7_soft_skills": <điểm từ 0 đến 0.5>,
    "c8_language_cv": <điểm từ 0 đến 0.5>,
    "c9_stability": <điểm từ 0 đến 0.5>,
    "c10_ai_overall": <điểm từ 0 đến 0.5>
  }},
  "reasons": {{
    "c1_technical_skills": "<Liệt kê kỹ năng ứng viên có. NẾU điểm < 2.0, BẮT BUỘC thêm 'Điểm trừ: [thiếu kỹ năng gì theo JD / lý do trừ điểm]'>",
    "c2_experience": "<Nêu số năm kinh nghiệm. NẾU điểm < 2.0, BẮT BUỘC thêm 'Điểm trừ: [thiếu sót gì so với JD / lý do trừ]'>",
    "c3_education": "<Trích dẫn bằng cấp. NẾU điểm < 1.0, BẮT BUỘC thêm 'Điểm trừ: [chưa đạt yêu cầu vượt trội / lý do trừ]'>",
    "c4_industry": "<Nêu ngành nghề đã làm. NẾU điểm < 1.0, BẮT BUỘC thêm 'Điểm trừ: [chênh lệch ngành nghề thế nào]'>",
    "c5_career_path": "<Nêu minh chứng thăng tiến. NẾU điểm < 1.0, BẮT BUỘC thêm 'Điểm trừ: [lý do trừ, vd thăng tiến chậm]'>",
    "c6_achievements": "<Nêu số liệu thành tích. NẾU điểm < 1.0, BẮT BUỘC thêm 'Điểm trừ: [thiếu mức độ thành tích theo yêu cầu]'>",
    "c7_soft_skills": "<Trích dẫn hành động. NẾU điểm < 0.5, BẮT BUỘC thêm 'Điểm trừ: [thiếu minh chứng cho kỹ năng mềm nào]'>",
    "c8_language_cv": "<Nhận xét CV & ngoại ngữ. NẾU điểm < 0.5, BẮT BUỘC thêm 'Điểm trừ: [lỗi form / ngoại ngữ kém]'>",
    "c9_stability": "<Nêu trung bình năm/công ty. NẾU điểm < 0.5, BẮT BUỘC thêm 'Điểm trừ: [rủi ro nhảy việc]'>",
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

Tạo đúng {num_gen} câu hỏi phỏng vấn về kinh nghiệm thực tế dựa trực tiếp vào thông tin có trong CV trên.
Yêu cầu:
- Điều chỉnh độ khó/chiều sâu phù hợp với cấp bậc {level} (Entry=cơ bản, Mid=dự án thực tế, Senior/Manager=lãnh đạo/chiến lược)
- Hỏi cụ thể về dự án, công nghệ, hoặc kinh nghiệm thực sự đề cập trong CV (không hỏi chung chung)
- Bắt đầu bằng: "Trong CV bạn có đề cập...", "Bạn từng làm...", "Bạn có kinh nghiệm với..." hoặc tương tự
- Câu hỏi phải giúp ứng viên kể chi tiết hơn về những gì họ đã thực sự làm
- Viết bằng tiếng Việt, ngắn gọn (1-2 câu mỗi câu hỏi)

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
    "q07": "Dựa trên CV của ứng viên, hãy tạo 1 câu hỏi sâu về 1 dự án nổi bật nhất hoặc kinh nghiệm thực tế quan trọng nhất của ứng viên, yêu cầu ứng viên mô tả khó khăn và cách giải quyết.",
    "q08": "Dựa trên CV của ứng viên, hãy tạo 1 câu hỏi tình huống thực tế liên quan mật thiết đến công nghệ/nghiệp vụ chính mà ứng viên đã làm, để kiểm tra cách họ áp dụng kiến thức vào thực tế."
}

LEVEL_ORDER = {"nắm vững": 10, "am hiểu": 7.5, "có biết qua": 5, "không biết": 0}

_JOB_LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")

THIRD_PARTY_WEBHOOK_URL = os.environ.get("THIRD_PARTY_WEBHOOK_URL", "")

DEEP_ANALYSIS_PROMPT = """Bạn là một Chuyên gia Tuyển dụng cấp cao. 
Nhiệm vụ của bạn là phân tích sâu CV của ứng viên đối chiếu với Mô tả công việc (JD), sau đó sinh ra những câu hỏi phỏng vấn chuyên sâu (deep analysis). Số lượng câu hỏi tùy thuộc vào số lượng những điểm đáng chú ý, nghi vấn hoặc thành tích nổi bật trong CV (cứ có điểm nào đáng hỏi thì sinh câu hỏi, không bị giới hạn số lượng).

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

EVALUATE_REPLY_PROMPT = """Bạn là Chuyên gia Tuyển dụng cấp cao. 
Nhiệm vụ của bạn là đánh giá câu trả lời của ứng viên cho các câu hỏi chuyên sâu (Deep Analysis) đã được gửi qua email.

YÊU CẦU:
1. Đối chiếu câu trả lời của ứng viên với CV của họ và yêu cầu của JD.
2. Đánh giá tính chân thực, mức độ hiểu biết chuyên môn, và khả năng giải quyết vấn đề.
3. Chỉ ra những điểm mạnh (red flags nếu có) từ câu trả lời.
4. Đưa ra kết luận: Câu trả lời có đáp ứng được kỳ vọng để mời phỏng vấn chính thức hay không.

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
