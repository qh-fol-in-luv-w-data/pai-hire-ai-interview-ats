# External API theo công ty

Mỗi công ty có API key riêng. Khóa chỉ có quyền đọc/ghi hồ sơ có cùng `company_id`; nếu dùng `app_id` của công ty khác, API trả `404`.

## 1. Tạo công ty và lấy API key (platform admin)

```bash
curl -sS -X POST "https://hire.ctpai.vn/admin/companies" \
  -H "X-Admin-Key: $PAI_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Công ty ABC","slug":"cong-ty-abc","key_name":"ATS production"}'
```

Trường `api_key` trong phản hồi chỉ hiển thị một lần. Lưu nó trong secret manager/biến môi trường, không đưa vào frontend hoặc Git.

## 2. Đẩy CV để chấm và nhận app_id

```bash
export PAI_API_KEY='pai_cong-ty-abc_...'
curl -sS -X POST "https://hire.ctpai.vn/api/v1/score-cv" \
  -H "Authorization: Bearer $PAI_API_KEY" \
  -F "cv_file=@./ung-vien.pdf" \
  -F "jd_text=Mo ta cong viec va yeu cau vi tri..." \
  -F "candidate_name=Nguyen Van A" \
  -F "candidate_email=a@example.com" \
  -F "level=Junior"
```

Lưu `app_id` trong phản hồi để tạo lịch và đọc báo cáo.

## 3. Tạo link phỏng vấn

```bash
curl -sS -X POST "https://hire.ctpai.vn/api/v1/schedule" \
  -H "Authorization: Bearer $PAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"APP-XXXXXXXX","start_time":"2026-08-12T09:00:00+07:00","end_time":"2026-08-12T10:00:00+07:00","position_id":"backend-developer","level":"Junior"}'
```

## 4. Đọc báo cáo

```bash
curl -sS "https://hire.ctpai.vn/api/v1/report/APP-XXXXXXXX" \
  -H "Authorization: Bearer $PAI_API_KEY"
```

`curl` của công ty A không thể xem, cấp lịch hoặc lấy báo cáo cho `app_id` của công ty B.
