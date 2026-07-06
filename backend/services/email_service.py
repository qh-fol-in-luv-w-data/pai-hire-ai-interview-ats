import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from backend.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, INTERVIEW_URL

def _smtp_send(msg: MIMEMultipart, to_email: str):
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo(); s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"[Email] Đã gửi → {to_email}")
    except Exception as e:
        print(f"[Email Error] {to_email}: {e}")


def send_pass_email(name: str, to_email: str, job_title: str, app_id: str, level: str = "Junior"):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Email] Chưa cấu hình SMTP — bỏ qua gửi mail cho {to_email}")
        return

    # Strip level prefix from pos param since interview.html reads level from ?lv=
    LEVELS = ("Entry", "Junior", "Mid", "Senior", "Manager", "Director")
    base_pos = job_title
    for lv in LEVELS:
        if job_title.startswith(lv + "_"):
            base_pos = job_title[len(lv)+1:]
            break
    interview_link = f"{INTERVIEW_URL}?ref={app_id}&pos={base_pos}&lv={level}"
    job_display    = job_title.replace("_", " ")
    today          = time.strftime("%d/%m/%Y")

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;">

  <!-- Logo bar -->
  <tr><td style="background:#131b2e;padding:24px 40px;display:flex;align-items:center;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#ffffff;font-size:16px;font-weight:700;letter-spacing:-.2px;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Phòng Nhân Sự · Tuyển Dụng</p>
      </td>
    </tr></table>
  </td></tr>

  <!-- Hero -->
  <tr><td style="padding:40px 40px 0;">
    <p style="margin:0 0 6px;color:#6b7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;">Thư mời phỏng vấn</p>
    <h1 style="margin:0 0 20px;color:#111827;font-size:24px;font-weight:700;line-height:1.3;">
      Kính gửi {name},
    </h1>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.75;">
      Cảm ơn bạn đã quan tâm và nộp hồ sơ ứng tuyển vị trí
      <strong style="color:#111827;">{job_display}</strong> tại PAI HR.
    </p>
    <p style="margin:16px 0 0;color:#374151;font-size:15px;line-height:1.75;">
      Sau khi xem xét hồ sơ của bạn, chúng tôi rất vui mừng thông báo rằng bạn đã
      <strong style="color:#0051d5;">đáp ứng các tiêu chí tuyển dụng</strong> của vị trí này
      và được mời tham gia vòng phỏng vấn tiếp theo.
    </p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:28px 40px 0;">
    <div style="height:1px;background:#e5e7eb;"></div>
  </td></tr>

  <!-- Interview info -->
  <tr><td style="padding:28px 40px 0;">
    <p style="margin:0 0 16px;color:#111827;font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">Thông tin buổi phỏng vấn</p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border-radius:8px 8px 0 0;border:1px solid #e5e7eb;border-bottom:none;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Hình thức</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">Phỏng vấn trực tuyến trực tuyến</p>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border:1px solid #e5e7eb;border-bottom:none;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Vị trí</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">{job_display}</p>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 16px;background:#f9fafb;border-radius:0 0 8px 8px;border:1px solid #e5e7eb;">
          <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Thời lượng dự kiến</p>
          <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">10 – 15 phút</p>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 24px;color:#374151;font-size:14px;line-height:1.75;">
      Bạn có thể thực hiện buổi phỏng vấn bất cứ lúc nào, theo đường link bên dưới.
      Hệ thống sẽ ghi lại câu trả lời của bạn để đội ngũ tuyển dụng đánh giá.
    </p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
      <tr><td align="center">
        <a href="{interview_link}"
           style="display:inline-block;background:#0051d5;color:#ffffff;text-decoration:none;
                  font-weight:700;font-size:15px;padding:15px 40px;border-radius:10px;letter-spacing:-.1px;">
          Bắt đầu phỏng vấn →
        </a>
      </td></tr>
    </table>
    <p style="margin:16px 0 0;text-align:center;font-size:12px;color:#9ca3af;">
      Nếu nút không hoạt động, copy link: <br/>
      <a href="{interview_link}" style="color:#0051d5;word-break:break-all;">{interview_link}</a>
    </p>
  </td></tr>

  <!-- Note -->
  <tr><td style="padding:0 40px 32px;">
    <div style="background:#fffbeb;border-left:3px solid #f59e0b;border-radius:4px;padding:14px 16px;">
      <p style="margin:0;color:#92400e;font-size:13px;line-height:1.6;">
        <strong>Lưu ý:</strong> Link phỏng vấn có hiệu lực trong <strong>7 ngày</strong> kể từ ngày nhận email này.
        Nếu cần hỗ trợ, vui lòng liên hệ đội tuyển dụng.
      </p>
    </div>
  </td></tr>

  <!-- Sig -->
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:13px;">{today}</span>
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;line-height:1.6;">
      Email tự động từ hệ thống PAI HR &nbsp;·&nbsp; Mã hồ sơ: <strong>{app_id}</strong><br/>
      Vui lòng không reply email này.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    plain = (
        f"Kính gửi {name},\n\n"
        f"Chúc mừng! Bạn đã được mời tham gia phỏng vấn vị trí {job_display} tại PAI HR.\n\n"
        f"Link phỏng vấn: {interview_link}\n\n"
        f"Thời lượng: 10–15 phút. Link có hiệu lực trong 7 ngày.\n\n"
        f"Trân trọng,\nĐội Tuyển Dụng PAI HR"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"]  = f"Mời phỏng vấn vị trí {job_display} tại PAI HR"
    msg["From"]     = f"PAI HR <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"[Email] Đã gửi → {to_email}")
    except Exception as e:
        print(f"[Email Error] {to_email}: {e}")


def send_fail_email(name: str, to_email: str, job_title: str, app_id: str):
    if not SMTP_USER or not SMTP_PASS:
        return

    job_display = job_title.replace("_", " ")
    today       = time.strftime("%d/%m/%Y")

    plain = (
        f"Kính gửi {name},\n\n"
        f"Cảm ơn bạn đã nộp hồ sơ ứng tuyển vị trí {job_display} tại PAI HR.\n\n"
        f"Sau khi xem xét, chúng tôi rất tiếc phải thông báo hồ sơ của bạn chưa đáp ứng "
        f"đủ yêu cầu tuyển dụng lần này.\n\n"
        f"Chúng tôi trân trọng sự quan tâm của bạn và khuyến khích bạn ứng tuyển "
        f"các vị trí phù hợp hơn trong tương lai.\n\n"
        f"Trân trọng,\nĐội Tuyển Dụng PAI HR"
    )

    html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;">

  <!-- Logo bar -->
  <tr><td style="background:#131b2e;padding:24px 40px;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#ffffff;font-size:16px;font-weight:700;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Phòng Nhân Sự · Tuyển Dụng</p>
      </td>
    </tr></table>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:40px 40px 0;">
    <p style="margin:0 0 6px;color:#6b7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;">Thông báo kết quả hồ sơ</p>
    <h1 style="margin:0 0 20px;color:#111827;font-size:22px;font-weight:700;line-height:1.3;">Kính gửi {name},</h1>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.75;">
      Cảm ơn bạn đã dành thời gian nộp hồ sơ ứng tuyển vị trí
      <strong style="color:#111827;">{job_display}</strong> tại PAI HR.
    </p>
    <p style="margin:16px 0 0;color:#374151;font-size:15px;line-height:1.75;">
      Sau khi xem xét kỹ lưỡng, chúng tôi rất tiếc phải thông báo rằng hồ sơ của bạn
      <strong style="color:#dc2626;">chưa đáp ứng đủ yêu cầu</strong> tuyển dụng cho vị trí này
      tại thời điểm hiện tại.
    </p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:28px 40px 0;"><div style="height:1px;background:#e5e7eb;"></div></td></tr>

  <!-- Note -->
  <tr><td style="padding:28px 40px;">
    <div style="background:#fef9f0;border-left:3px solid #f59e0b;border-radius:4px;padding:14px 16px;">
      <p style="margin:0;color:#92400e;font-size:13px;line-height:1.7;">
        Đây không phải quyết định cuối cùng về năng lực của bạn. Chúng tôi khuyến khích bạn
        tiếp tục phát triển kỹ năng và <strong>ứng tuyển lại</strong> khi có vị trí phù hợp hơn
        trong tương lai tại <a href="#" style="color:#0051d5;">PAI HR</a>.
      </p>
    </div>
  </td></tr>

  <!-- Sig -->
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:13px;">{today}</span>
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">
      Email tự động từ hệ thống PAI HR &nbsp;·&nbsp; Mã hồ sơ: <strong>{app_id}</strong>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"]  = f"Kết quả hồ sơ ứng tuyển vị trí {job_display} tại PAI HR"
    msg["From"]     = f"PAI HR <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    _smtp_send(msg, to_email)


def send_interview_reminder(name: str, to_email: str, job_title: str, interview_link: str):
    """§27 — Email nhắc nhở T-24h trước phỏng vấn: xác nhận lịch + hướng dẫn kỹ thuật."""
    if not SMTP_USER or not SMTP_PASS:
        return
    job_display = job_title.replace("_", " ")
    today       = time.strftime("%d/%m/%Y")

    html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;">
  <tr><td style="background:#131b2e;padding:24px 40px;border-bottom:3px solid #0051d5;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#fff;font-size:16px;font-weight:700;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Nhắc nhở phỏng vấn</p>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:36px 40px 0;">
    <p style="margin:0 0 6px;color:#6b7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;">Nhắc nhở phỏng vấn</p>
    <h1 style="margin:0 0 16px;color:#111827;font-size:22px;font-weight:700;">Kính gửi {name},</h1>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.75;">
      Đây là email nhắc nhở buổi phỏng vấn trực tuyến trực tuyến vị trí
      <strong style="color:#0051d5;">{job_display}</strong> của bạn.
      Link phỏng vấn vẫn còn hiệu lực và sẵn sàng để bạn sử dụng.
    </p>
  </td></tr>
  <tr><td style="padding:24px 40px 0;">
    <div style="background:#eff6ff;border-radius:8px;padding:20px;">
      <p style="margin:0 0 12px;color:#1e40af;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">Chuẩn bị trước khi phỏng vấn</p>
      <ul style="margin:0;padding-left:20px;color:#374151;font-size:13px;line-height:1.9;">
        <li>Sử dụng trình duyệt <strong>Chrome hoặc Edge</strong> phiên bản mới nhất</li>
        <li>Cho phép trình duyệt <strong>truy cập microphone</strong> khi được hỏi</li>
        <li>Chọn nơi <strong>yên tĩnh</strong>, không có tiếng ồn xung quanh</li>
        <li>Buổi phỏng vấn có <strong>8 câu hỏi</strong>, thời lượng khoảng <strong>15–20 phút</strong></li>
        <li>Câu trả lời của bạn sẽ được <strong>ghi âm</strong> để đội tuyển dụng đánh giá</li>
      </ul>
    </div>
  </td></tr>
  <tr><td style="padding:28px 40px;">
    <table cellpadding="0" cellspacing="0" style="width:100%;"><tr><td align="center">
      <a href="{interview_link}"
         style="display:inline-block;background:#0051d5;color:#fff;text-decoration:none;
                font-weight:700;font-size:15px;padding:14px 40px;border-radius:10px;">
        Vào phỏng vấn ngay →
      </a>
    </td></tr></table>
    <p style="margin:14px 0 0;text-align:center;font-size:12px;color:#9ca3af;">
      <a href="{interview_link}" style="color:#0051d5;word-break:break-all;">{interview_link}</a>
    </p>
  </td></tr>
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:13px;">{today}</span>
    </p>
  </td></tr>
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:14px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">Email tự động từ hệ thống PAI HR · Vui lòng không reply.</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    plain = (
        f"Kính gửi {name},\n\n"
        f"Nhắc nhở: bạn có buổi phỏng vấn trực tuyến vị trí {job_display}.\n"
        f"Link: {interview_link}\n\n"
        f"Chuẩn bị: Chrome/Edge, cho phép microphone, nơi yên tĩnh, 10–15 phút.\n\n"
        f"Trân trọng, Đội Tuyển Dụng PAI HR"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = f"[Nhắc nhở] Phỏng vấn trực tuyến vị trí {job_display} — PAI HR"
    msg["From"]     = f"PAI HR <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    _smtp_send(msg, to_email)


def send_reinterview_email(name: str, to_email: str, job_title: str,
                           interview_link: str, reason: str = "", scope: str = "07,08"):
    """Email thông báo ứng viên được mời phỏng vấn lại (re-interview) với link mới."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Email] SMTP chưa cấu hình — bỏ qua re-interview mail cho {to_email}")
        return
    job_display = job_title.replace("_", " ")
    today       = time.strftime("%d/%m/%Y")
    scope_label = f"câu {scope}" if scope else "toàn bộ câu hỏi"
    reason_row  = f"""
      <tr><td style="padding:10px 16px;background:#fefce8;border:1px solid #fef08a;border-radius:8px;margin-top:8px;">
        <p style="margin:0;color:#713f12;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.4px;">Lý do</p>
        <p style="margin:4px 0 0;color:#92400e;font-size:14px;">{reason}</p>
      </td></tr>""" if reason.strip() else ""

    html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;">

  <tr><td style="background:#131b2e;padding:24px 40px;border-bottom:3px solid #f59e0b;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#fff;font-size:16px;font-weight:700;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Mời phỏng vấn lại</p>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:36px 40px 0;">
    <div style="display:inline-block;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:4px 12px;margin-bottom:16px;">
      <p style="margin:0;color:#92400e;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;">Phỏng vấn lại</p>
    </div>
    <h1 style="margin:0 0 16px;color:#111827;font-size:22px;font-weight:700;">Kính gửi {name},</h1>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.8;">
      Sau khi xem xét kỹ hơn hồ sơ của bạn, đội tuyển dụng <strong style="color:#111827;">PAI HR</strong>
      muốn mời bạn tham gia thêm một buổi phỏng vấn trực tuyến bổ sung cho vị trí
      <strong style="color:#0051d5;">{job_display}</strong>.
    </p>
  </td></tr>

  <tr><td style="padding:20px 40px 0;">
    <table cellpadding="0" cellspacing="0" style="width:100%;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
      <tr><td colspan="2" style="background:#f9fafb;padding:10px 16px;border-bottom:1px solid #e5e7eb;">
        <p style="margin:0;color:#374151;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">Chi tiết buổi phỏng vấn</p>
      </td></tr>
      <tr><td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;width:40%;">
        <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;">Phạm vi</p>
        <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">{scope_label}</p>
      </td><td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;">
        <p style="margin:0;color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;">Hình thức</p>
        <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:600;">Phỏng vấn trực tuyến trực tuyến</p>
      </td></tr>
      {reason_row}
    </table>
  </td></tr>

  <tr><td style="padding:28px 40px;">
    <table cellpadding="0" cellspacing="0" style="width:100%;"><tr><td align="center">
      <a href="{interview_link}"
         style="display:inline-block;background:#f59e0b;color:#fff;text-decoration:none;
                font-weight:700;font-size:15px;padding:14px 40px;border-radius:10px;letter-spacing:-.1px;">
        Vào phỏng vấn lại ngay →
      </a>
    </td></tr></table>
    <p style="margin:14px 0 0;text-align:center;font-size:12px;color:#9ca3af;">
      <a href="{interview_link}" style="color:#0051d5;word-break:break-all;">{interview_link}</a>
    </p>
  </td></tr>

  <tr><td style="padding:0 40px 28px;">
    <div style="background:#eff6ff;border-radius:8px;padding:16px 20px;">
      <p style="margin:0 0 10px;color:#1e40af;font-size:12px;font-weight:700;text-transform:uppercase;">Lưu ý kỹ thuật</p>
      <ul style="margin:0;padding-left:18px;color:#374151;font-size:13px;line-height:1.9;">
        <li>Dùng trình duyệt <strong>Chrome hoặc Edge</strong></li>
        <li>Cho phép <strong>truy cập microphone</strong> khi được hỏi</li>
        <li>Chọn nơi <strong>yên tĩnh</strong>, không có tiếng ồn</li>
      </ul>
    </div>
  </td></tr>

  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:12px;">{today}</span>
    </p>
  </td></tr>
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:14px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">Email tự động từ hệ thống PAI HR · Vui lòng không reply.</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    plain = (
        f"Kính gửi {name},\n\n"
        f"Đội tuyển dụng PAI HR mời bạn tham gia phỏng vấn lại vị trí {job_display}.\n"
        f"Phạm vi: {scope_label}.\n"
        + (f"Lý do: {reason}\n" if reason.strip() else "")
        + f"\nLink phỏng vấn: {interview_link}\n\n"
        f"Lưu ý: dùng Chrome/Edge, cho phép microphone, nơi yên tĩnh.\n\n"
        f"Trân trọng, Đội Tuyển Dụng PAI HR"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = f"[Mời phỏng vấn lại] {job_display} · PAI HR"
    msg["From"]     = f"PAI HR <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    _smtp_send(msg, to_email)
    print(f"[Email] Re-interview mail → {to_email}")


def send_interview_result(name: str, to_email: str, job_title: str, decision: str, interview_id: str):
    """§27 — Email thông báo kết quả sau khi Recruiter PATCH status=passed/failed."""
    if not SMTP_USER or not SMTP_PASS:
        return
    job_display = job_title.replace("_", " ")
    today       = time.strftime("%d/%m/%Y")
    is_pass     = decision in ("passed", "pass")

    if is_pass:
        subject   = f"Kết quả phỏng vấn — Chúc mừng! {job_display} · PAI HR"
        color     = "#16a34a"
        icon_bg   = "#dcfce7"
        eyebrow   = "Kết quả phỏng vấn"
        headline  = "Chúc mừng! Bạn đã vượt qua vòng phỏng vấn trực tuyến"
        body_text = (
            f"Chúng tôi vui mừng thông báo bạn đã <strong style=\"color:{color};\">vượt qua</strong> "
            f"vòng phỏng vấn trực tuyến cho vị trí <strong>{job_display}</strong>. "
            f"Đội tuyển dụng sẽ liên hệ với bạn trong thời gian sớm nhất để sắp xếp các bước tiếp theo."
        )
        icon_char = "✓"
    else:
        subject   = f"Kết quả phỏng vấn — {job_display} · PAI HR"
        color     = "#dc2626"
        icon_bg   = "#fee2e2"
        eyebrow   = "Kết quả phỏng vấn"
        headline  = "Cảm ơn bạn đã tham gia phỏng vấn"
        body_text = (
            f"Sau khi xem xét buổi phỏng vấn, chúng tôi rất tiếc phải thông báo rằng "
            f"kết quả của bạn <strong style=\"color:{color};\">chưa đáp ứng yêu cầu</strong> "
            f"cho vị trí <strong>{job_display}</strong> tại thời điểm này. "
            f"Chúng tôi trân trọng thời gian bạn đã dành và khuyến khích bạn ứng tuyển trở lại khi có vị trí phù hợp."
        )
        icon_char = "✕"

    html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;">
  <tr><td style="background:#131b2e;padding:24px 40px;border-bottom:3px solid {color};">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:36px;height:36px;background:#0051d5;border-radius:8px;text-align:center;vertical-align:middle;">
        <span style="color:#fff;font-size:18px;font-weight:800;line-height:36px;">P</span>
      </td>
      <td style="padding-left:12px;">
        <p style="margin:0;color:#fff;font-size:16px;font-weight:700;">PAI HR</p>
        <p style="margin:0;color:rgba(255,255,255,.45);font-size:11px;">Kết quả phỏng vấn</p>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:40px 40px 0;text-align:center;">
    <div style="width:56px;height:56px;background:{icon_bg};border-radius:50%;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
      <span style="color:{color};font-size:24px;font-weight:900;">{icon_char}</span>
    </div>
    <p style="margin:0 0 6px;color:#6b7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;">{eyebrow}</p>
    <h1 style="margin:0 0 16px;color:#111827;font-size:21px;font-weight:700;">{headline}</h1>
  </td></tr>
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.75;">Kính gửi {name},</p>
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.75;">{body_text}</p>
    <div style="margin-top:24px;padding:14px 16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#6b7280;">
        Vị trí ứng tuyển: <strong style="color:#111827;">{job_display}</strong><br/>
        Mã phỏng vấn: <span style="font-family:monospace;color:#374151;">{interview_id}</span>
      </p>
    </div>
  </td></tr>
  <tr><td style="padding:0 40px 32px;">
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.75;">
      Trân trọng,<br/>
      <strong style="color:#111827;">Đội Tuyển Dụng PAI HR</strong><br/>
      <span style="color:#6b7280;font-size:13px;">{today}</span>
    </p>
  </td></tr>
  <tr><td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:14px 40px;">
    <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">Email tự động từ hệ thống PAI HR · Vui lòng không reply.</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    if is_pass:
        plain = (
            f"Kính gửi {name},\n\n"
            f"Chúng tôi vui mừng thông báo bạn đã vượt qua vòng phỏng vấn trực tuyến cho vị trí {job_display}. "
            f"Đội tuyển dụng sẽ liên hệ với bạn trong thời gian sớm nhất để sắp xếp các bước tiếp theo.\n\n"
            f"Vị trí ứng tuyển: {job_display}\n"
            f"Mã phỏng vấn: {interview_id}\n\n"
            f"Trân trọng,\n"
            f"Đội Tuyển Dụng PAI HR"
        )
    else:
        plain = (
            f"Kính gửi {name},\n\n"
            f"Sau khi xem xét buổi phỏng vấn, chúng tôi rất tiếc phải thông báo rằng kết quả của bạn "
            f"chưa đáp ứng yêu cầu cho vị trí {job_display} tại thời điểm này. "
            f"Chúng tôi trân trọng thời gian bạn đã dành và khuyến khích bạn ứng tuyển trở lại khi có vị trí phù hợp.\n\n"
            f"Vị trí ứng tuyển: {job_display}\n"
            f"Mã phỏng vấn: {interview_id}\n\n"
            f"Trân trọng,\n"
            f"Đội Tuyển Dụng PAI HR"
        )
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"PAI HR <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    _smtp_send(msg, to_email)


