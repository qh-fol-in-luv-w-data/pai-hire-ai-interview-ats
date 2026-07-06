# PAI HR - Phỏng vấn trực tuyến

Hệ thống phỏng vấn trực tuyến sử dụng AI để đánh giá ứng viên. Hệ thống bao gồm giao diện ứng viên (Candidate Interview), giao diện Admin (quản lý kết quả) và backend xử lý âm thanh, văn bản (STT/TTS) và đánh giá ứng viên tự động.

## Cấu trúc thư mục
- `frontend/`: Giao diện ứng viên (`interview.html`) và giao diện Admin (`admin.html`, `report_print.html`).
- `backend/`: API Backend xây dựng trên nền FastAPI. Cấu trúc chia thành các module:
  - `main.py`: Entrypoint cấu hình server.
  - `database.py`: Quản lý SQLite và các scripts tạo bảng (migrations).
  - `config.py`: Quản lý các biến môi trường và thiết lập chung.
  - `routers/`: Chứa các API con (`admin.py`, `interview.py`, `jobs.py`, `feedback.py`).
  - `services/`: Chứa các hàm xử lý logic lõi (`ai_service.py`, `email_service.py`, `document_service.py`, `prep_service.py`).
- `outputs/`: Chứa dữ liệu file ghi âm phỏng vấn, hồ sơ CV ứng viên, file tạm.

## Yêu cầu môi trường
- Python 3.9+
- Các khoá API (API Keys):
  - `OPENAI_API_KEY`: Dùng cho đánh giá ứng viên, chuẩn hoá văn bản, sinh câu hỏi phụ bằng GPT-4o.
  - `ELEVENLABS_API_KEY`: Dùng cho việc Speech-to-Text (STT) tiếng Việt (model `scribe_v2`).

## Cơ sở dữ liệu (Database)
- Hệ thống sử dụng **SQLite3** làm cơ sở dữ liệu mặc định để dễ dàng triển khai mà không cần cài đặt thêm phần mềm DB.
- File DB sẽ được **tự động khởi tạo** với tên `ats_phongvan.db` tại thư mục gốc ngay lần đầu chạy server (hàm `init_db` sẽ tự tạo các bảng nếu chưa có).
- **Để reset (xoá) toàn bộ dữ liệu**: Bạn chỉ cần tắt server, xoá file `ats_phongvan.db` trong thư mục gốc, rồi chạy server lại. Hệ thống sẽ tự động tạo file và các bảng trống lại từ đầu.
- Schema bao gồm các bảng: `candidates`, `interviews`, `answers`, `cv_applications`, `interview_prep`, `incidents`, `candidate_feedback`.

## Cài đặt và Khởi chạy

1. **Cài đặt thư viện Python**
```bash
pip install -r requirements.txt
```
*(Nếu cài đặt báo thiếu thư viện, có thể bạn đang dùng môi trường ảo cũ, hãy tạo một venv mới bằng `python -m venv venv` trước)*

2. **Cấu hình môi trường**
Tạo file `.env` ở thư mục gốc (cùng cấp với thư mục `backend`) với nội dung:
```env
# API Keys (Bắt buộc)
OPENAI_API_KEY=sk-xxx
ELEVENLABS_API_KEY=xxx

# Cấu hình Admin
ADMIN_KEY=admin@2024

# (Tuỳ chọn) Email cấu hình để gửi báo cáo cho ứng viên
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
```

3. **Chạy Backend Server**
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```
*Backend mặc định sẽ chạy ở `http://localhost:8080` và sẽ tự động host nội dung tĩnh trong thư mục `frontend/` thông qua mount `/ui`.*

## Truy cập ứng dụng
- **Giao diện Ứng viên (Phỏng vấn)**:
  Mở trình duyệt truy cập: `http://localhost:8080/ui/interview.html?reiv=test`
- **Giao diện Admin (Quản lý)**:
  Mở trình duyệt truy cập: `http://localhost:8080/ui/admin.html`
  *(Sử dụng admin key đã được cấu hình trong hệ thống, mặc định nhập: `admin@2024`)*

## Các tính năng chính
- **Real-time STT Normalization**: Chuẩn hoá văn bản giọng nói tức thời khi ứng viên kết thúc câu.
- **Continuous Pushbacks**: Đặt câu hỏi phản biện liên tục đào sâu vào câu trả lời mập mờ, dựa trên lịch sử trao đổi đệ quy.
- **NPS Survey**: Thu thập đánh giá từ ứng viên sau phỏng vấn.
- **Report Generation**: Sinh báo cáo tổng quan năng lực, điểm mạnh/yếu dựa vào lịch sử vấn đáp.
