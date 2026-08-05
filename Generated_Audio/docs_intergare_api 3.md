# Hướng dẫn Tích hợp AI Proctoring cho Nền tảng Phỏng vấn

Dưới đây là tài liệu API và hướng dẫn nhúng Iframe dành cho các nền tảng bên thứ 3 (Hệ thống thi/phỏng vấn).

## 1. Khởi tạo Phiên giám sát (Backend to Backend)

Khi có một ứng viên chuẩn bị vào thi/phỏng vấn, Backend của bạn cần gọi API của chúng tôi để khởi tạo cấu hình Webhook.

**Endpoint:** `POST https://service.ctpai.vn/detection/rule-engine/api/v1/sessions`
**Headers:**
- `Content-Type: application/json`
- `X-API-Key: super-secret-api-key` (Được cấu hình trong `.env`)

**Body (JSON):**
{
  "session_id": "interview_canidate_001",
  "webhook_url": "https://your-domain.com/api/webhooks/ai-proctoring",
  "alert_threshold_seconds": 3
}
```

*Lưu ý: `alert_threshold_seconds` là tùy chọn (Option), dùng để cấu hình số giây liên tục mà hệ thống chờ trước khi cảnh báo một lỗi (ví dụ: mất mặt 3 giây liên tục mới báo). Mặc định là 3, và hệ thống chỉ chấp nhận giá trị >= 3.*

**Response:**
```json
{
  "status": "success",
  "message": "Session created",
  "session_id": "interview_canidate_001",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXNzaW9uX2lkIjoiaW50...",
  "embed_url": "https://service.ctpai.vn/detection/?token=eyJhbGciOiJIUzI1Ni...&autostart=true&debug=0"
}
```

Hệ thống của chúng tôi sẽ tự động sinh ra một JWT Token (có hạn sử dụng 2 tiếng) dành riêng cho `session_id` này. Bạn sử dụng giá trị `embed_url` trả về để nhúng vào bước tiếp theo.

## 2. Nhúng Giao diện Camera (Frontend)

Khi ứng viên mở trang thi trên hệ thống của bạn, bạn sử dụng thẻ `<iframe>` để nhúng link `embed_url` vừa nhận được.

```html
<!-- Chèn embed_url nhận được từ API -->
<iframe 
  src="https://service.ctpai.vn/detection/?token=eyJhbGciOiJIUzI1Ni...&autostart=true&debug=0" 
  width="800" 
  height="600" 
  allow="camera; microphone" 
  frameborder="0">
</iframe>
```
**Lưu ý quan trọng:** Bắt buộc phải có thuộc tính `allow="camera; microphone"` trong thẻ iframe để trình duyệt cấp quyền truy cập webcam cho Iframe. Tham số `autostart=true` sẽ tự động bật camera ngay lập tức, và tham số `debug=0` sẽ giúp ẩn giao diện debug/log của AI, mang lại giao diện tinh gọn nhất cho thí sinh.

## 3. Nhận Cảnh báo Thời gian thực (Webhook)

Trong suốt quá trình thi, nếu AI phát hiện có vi phạm (VD: Nhiều khuôn mặt, Mất khuôn mặt, Dùng ảnh giả), hệ thống của chúng tôi sẽ lập tức bắn một HTTP POST Request tới `webhook_url` mà bạn đã đăng ký ở Bước 1.

**Payload nhận được tại Server của bạn:**
```json
{
  "session_id": "interview_canidate_001",
  "alert_type": "MULTI_FACE",
  "timestamp": "2026-07-21T03:32:00.123Z",
  "snapshot_id": "16234234_snapshot.jpg"
}
```
**Xử lý tại Server của bạn:**
Từ `alert_type` này, bạn có thể lập tức kích hoạt Socket.io (hoặc cơ chế tương tự) để hiện popup cảnh cáo thí sinh, hoặc đánh dấu vi phạm vào báo cáo bài thi. Dữ liệu hình ảnh bằng chứng có thể được tải về sau bằng cách gọi API Storage của chúng tôi kèm theo `snapshot_id`.
