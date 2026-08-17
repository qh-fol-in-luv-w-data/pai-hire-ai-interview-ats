const labels: Record<string, string> = {
  pending: 'Đang xử lý', pending_review: 'Chờ xem xét', waiting_for_reply_passed: 'Chờ ứng viên bổ sung', waiting_for_reply_failed: 'Chờ ứng viên bổ sung',
  pending_hr_approval_passed: 'Chờ HR duyệt · Đạt', pending_hr_approval_failed: 'Chờ HR duyệt · Chưa đạt',
  interview_link_sent: 'Đã gửi link phỏng vấn', scheduled: 'Đã lên lịch', submitted: 'Đã nộp bài', evaluated: 'Đã đánh giá', passed: 'Đạt', failed: 'Không đạt', error: 'Có lỗi', reviewing: 'Đang xem xét',
};
export const statusLabel = (value?: string) => labels[value || ''] || value || 'Chưa xác định';
export type StatusTone = 'success'|'danger'|'warning'|'info'|'neutral';
export const statusTone = (value?: string):StatusTone => value === 'passed' || value === 'evaluated' || value === 'interview_link_sent' ? 'success' : value === 'failed' || value === 'error' ? 'danger' : value?.includes('waiting') || value?.includes('pending') ? 'warning' : 'neutral';
