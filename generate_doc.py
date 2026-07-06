"""Generate PAI HR project documentation as .docx"""
import io, os
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import docx.oxml

# ── helpers ───────────────────────────────────────────────────
def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def add_heading(doc, text, level, color_hex=None):
    p = doc.add_heading(text, level=level)
    if color_hex:
        for run in p.runs:
            run.font.color.rgb = RGBColor.from_string(color_hex)
    return p

def add_bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    if bold_prefix:
        run = p.add_run(bold_prefix + ': ')
        run.bold = True
    p.add_run(text)
    return p

def add_table_row(table, cells, bold=False, header=False, bg=None):
    row = table.add_row()
    for i, val in enumerate(cells):
        cell = row.cells[i]
        cell.text = str(val)
        cell.paragraphs[0].runs[0].bold = bold or header
        if header:
            cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        if bg:
            set_cell_bg(cell, bg)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    return row

# ── document ──────────────────────────────────────────────────
doc = Document()

# Page margins
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

# Default style
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)

# ══════════════════════════════════════════════════════════════
# TITLE PAGE
# ══════════════════════════════════════════════════════════════
doc.add_paragraph()
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('PAI HR — AI RECRUITMENT SYSTEM')
run.bold = True
run.font.size = Pt(24)
run.font.color.rgb = RGBColor(0x00, 0x51, 0xD5)

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run2 = subtitle.add_run('Tài Liệu Kỹ Thuật & Luồng Nghiệp Vụ')
run2.font.size = Pt(14)
run2.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

doc.add_paragraph()
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run('Phiên bản 1.0  ·  Tháng 6/2026').font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 1. TỔNG QUAN DỰ ÁN
# ══════════════════════════════════════════════════════════════
add_heading(doc, '1. Tổng Quan Dự Án', 1, '0051D5')

doc.add_paragraph(
    'PAI HR là hệ thống tuyển dụng tích hợp AI, tự động hóa toàn bộ quy trình '
    'từ đăng tin việc làm, nhận hồ sơ, chấm điểm CV bằng GPT-4o, gửi email mời '
    'phỏng vấn, đến phỏng vấn AI trực tuyến và lưu trữ kết quả cho HR xem xét.'
)

add_heading(doc, '1.1 Mục tiêu', 2)
add_bullet(doc, 'Tự động hóa sàng lọc CV — giảm thời gian xử lý hồ sơ thủ công.')
add_bullet(doc, 'Đảm bảo tính nhất quán — mọi ứng viên được đánh giá theo cùng rubric.')
add_bullet(doc, 'Trải nghiệm ứng viên liền mạch — từ apply → email → phỏng vấn không cần tải app.')
add_bullet(doc, 'Dashboard admin real-time — HR theo dõi pipeline tuyển dụng tập trung.')

add_heading(doc, '1.2 Tech Stack', 2)
t = doc.add_table(rows=1, cols=3)
t.style = 'Table Grid'
hdr = t.rows[0].cells
hdr[0].text = 'Tầng'; hdr[1].text = 'Công nghệ'; hdr[2].text = 'Mục đích'
for c in hdr:
    c.paragraphs[0].runs[0].bold = True
    set_cell_bg(c, '0051D5')
    c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)

rows = [
    ('Backend',  'Python 3.12 + FastAPI + Uvicorn', 'REST API, serve HTML, HTTPS'),
    ('Database', 'SQLite (WAL mode)',                'Lưu CV, phỏng vấn, câu trả lời'),
    ('AI',       'OpenAI GPT-4o',                   'Chấm điểm CV tự động'),
    ('TTS',      'OpenAI TTS-1-HD (nova)',           'Giọng đọc câu hỏi phỏng vấn'),
    ('Frontend', 'Vanilla JS + Tailwind CSS CDN',   'Admin UI & Interview page'),
    ('Email',    'Gmail SMTP + App Password',        'Gửi mail mời / từ chối'),
    ('HTTPS',    'mkcert self-signed cert',          'Cho phép microphone trên mobile'),
]
for r in rows:
    add_table_row(t, r)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 2. KIẾN TRÚC HỆ THỐNG
# ══════════════════════════════════════════════════════════════
add_heading(doc, '2. Kiến Trúc Hệ Thống', 1, '0051D5')

doc.add_paragraph(
    'Hệ thống chạy trên một máy chủ duy nhất, mở 1 port HTTPS (8000). '
    'Frontend Admin UI được serve dưới đường dẫn /ui/, còn trang phỏng vấn '
    'được serve tại /interview. Toàn bộ API và file tĩnh (audio câu hỏi) '
    'đều đi qua cùng một process FastAPI.'
)

add_heading(doc, '2.1 Sơ đồ kiến trúc', 2)

# SVG architecture diagram as placeholder description
arch_p = doc.add_paragraph()
arch_p.add_run('[Sơ đồ kiến trúc — xem file SVG đính kèm: architecture.svg]').italic = True

# Architecture text diagram
arch_text = doc.add_paragraph()
arch_text.style = doc.styles['No Spacing']
arch_text.paragraph_format.left_indent = Cm(1)
arch_run = arch_text.add_run(
    '┌──────────────────────────────────────────────────────────┐\n'
    '│                     CLIENT (Browser)                      │\n'
    '│  Admin UI (port 8000/ui/)   Interview (port 8000/interview)│\n'
    '└──────────────┬───────────────────────────┬───────────────┘\n'
    '               │  HTTPS (TLS)              │\n'
    '┌──────────────▼───────────────────────────▼───────────────┐\n'
    '│              FastAPI + Uvicorn (:8000)                    │\n'
    '│  /ui/*  StaticFiles    /interview  HTMLResponse           │\n'
    '│  /audio StaticFiles    /jobs  /apply  /admin/*  /health   │\n'
    '└──────┬──────────────────────┬──────────────────┬─────────┘\n'
    '       │                      │                  │\n'
    '  ┌────▼────┐          ┌──────▼──────┐    ┌─────▼──────┐\n'
    '  │ SQLite  │          │  OpenAI API  │    │ Gmail SMTP │\n'
    '  │  .db    │          │   GPT-4o    │    │   :587     │\n'
    '  └─────────┘          │  TTS-1-HD   │    └────────────┘\n'
    '                        └─────────────┘\n'
)
arch_run.font.name = 'Courier New'
arch_run.font.size = Pt(8)

add_heading(doc, '2.2 Cấu trúc thư mục', 2)
folder_p = doc.add_paragraph()
folder_p.style = doc.styles['No Spacing']
folder_p.paragraph_format.left_indent = Cm(1)
fr = folder_p.add_run(
    'ats_phongvan/\n'
    '├── backend/\n'
    '│   └── interview_api.py       # FastAPI app chính\n'
    '├── frontend/\n'
    '│   ├── ats_ui.html            # Admin UI\n'
    '│   └── interview.html         # Trang phỏng vấn\n'
    '├── inputs/\n'
    '│   └── audios/                # MP3 câu hỏi phỏng vấn\n'
    '│       ├── intro.mp3\n'
    '│       └── Junior_[Pos]_[N]_[Type].mp3\n'
    '├── outputs/\n'
    '│   ├── cv_applications/       # CV ứng viên đã upload\n'
    '│   └── interviews/\n'
    '│       └── IV-xxxx/           # Thư mục mỗi buổi phỏng vấn\n'
    '│           ├── cv.pdf\n'
    '│           └── answer_01-06.webm\n'
    '├── cert.pem / key.pem         # SSL certificate\n'
    '├── ats_phongvan.db            # SQLite database\n'
    '└── .env                       # API keys & config\n'
)
fr.font.name = 'Courier New'
fr.font.size = Pt(9)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 3. LUỒNG NGHIỆP VỤ
# ══════════════════════════════════════════════════════════════
add_heading(doc, '3. Luồng Nghiệp Vụ Đầy Đủ', 1, '0051D5')

add_heading(doc, '3.1 Luồng Ứng Viên (Candidate Journey)', 2)

steps = [
    ('BƯỚC 1', 'Xem Việc Làm',
     'Ứng viên truy cập trang Admin UI (cổng Guest), xem danh sách việc làm, '
     'lọc theo ngành nghề, đọc mô tả công việc.'),
    ('BƯỚC 2', 'Nộp Hồ Sơ',
     'Ứng viên điền thông tin (họ tên, email, SĐT), upload CV (PDF/DOCX ≤10MB), '
     'nhấn "Ứng Tuyển Ngay". Hệ thống tạo Application ID (APP-xxxxxxxx).'),
    ('BƯỚC 3', 'AI Chấm CV (Background)',
     'FastAPI BackgroundTasks gọi GPT-4o với rubric 10 điểm. Backend tính lại '
     'tổng từ sub-scores (không tin điểm AI). Kết quả lưu vào cv_applications.'),
    ('BƯỚC 4A', 'Email Đạt (Score ≥ 7.5)',
     'send_pass_email() gửi thư mời phỏng vấn với link: '
     'https://[IP]:8000/interview?ref=APP-xxx&pos=[JOB_ID]'),
    ('BƯỚC 4B', 'Email Rớt (Score < 7.5)',
     'send_fail_email() gửi thư từ chối lịch sự, khuyến khích ứng tuyển lần sau.'),
    ('BƯỚC 5', 'Phỏng Vấn AI',
     'Ứng viên bấm link trong mail → trang phỏng vấn load, tự skip Step 1 '
     '(CV đã có), vào thẳng 6 câu hỏi audio. Trả lời từng câu bằng ghi âm.'),
    ('BƯỚC 6', 'Nộp Bài',
     'Sau khi trả lời đủ 6 câu, nhấn "Nộp bài phỏng vấn". Backend lưu CV '
     '(copy từ application) + 6 file webm vào outputs/interviews/IV-xxxx/.'),
]

t2 = doc.add_table(rows=1, cols=3)
t2.style = 'Table Grid'
for i, h in enumerate(['Bước', 'Tên', 'Mô tả']):
    t2.rows[0].cells[i].text = h
    t2.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    set_cell_bg(t2.rows[0].cells[i], '131B2E')
    t2.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)

bg_alt = ['EFF6FF', 'FFFFFF']
for idx, (step, name, desc) in enumerate(steps):
    row = t2.add_row()
    row.cells[0].text = step
    row.cells[0].paragraphs[0].runs[0].bold = True
    row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x00,0x51,0xD5)
    row.cells[1].text = name
    row.cells[1].paragraphs[0].runs[0].bold = True
    row.cells[2].text = desc
    for c in row.cells:
        set_cell_bg(c, bg_alt[idx % 2])

add_heading(doc, '3.2 Luồng Admin (HR Journey)', 2)

admin_steps = [
    ('Đăng nhập', 'Nhập Admin Key → Hiện toàn bộ sidebar (Dashboard, Recruitment, Chấm CV, …)'),
    ('Dashboard', 'Xem KPI: tổng CV, tỷ lệ đạt, đang chờ, điểm trung bình. Pipeline tuyển dụng theo bars.'),
    ('Chấm CV',   'Xem danh sách CV với điểm AI. Lọc theo trạng thái/vị trí. Xem chi tiết: breakdown 10 tiêu chí + AI summary.'),
    ('Recruitment', 'Xem danh sách buổi phỏng vấn. Nghe lại câu trả lời. Chấm điểm thủ công từng câu. Cập nhật status.'),
    ('Guest mode', 'Người dùng khách chỉ thấy Việc Làm. Không cần đăng nhập để xem JD và apply.'),
]

for step, desc in admin_steps:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(step + ': ').bold = True
    p.add_run(desc)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 4. DATABASE SCHEMA
# ══════════════════════════════════════════════════════════════
add_heading(doc, '4. Database Schema (SQLite)', 1, '0051D5')

schema_tables = [
    ('cv_applications', 'Lưu hồ sơ ứng tuyển và kết quả chấm CV', [
        ('id',             'TEXT PK',  'APP-xxxxxxxx'),
        ('job_id',         'TEXT',     'VD: Junior_AIML_Engineer'),
        ('name',           'TEXT',     'Họ tên ứng viên'),
        ('email',          'TEXT',     'Email liên lạc'),
        ('phone',          'TEXT',     'Số điện thoại'),
        ('cv_filename',    'TEXT',     'Tên file CV gốc'),
        ('cv_path',        'TEXT',     'Đường dẫn file CV (relative)'),
        ('cv_score',       'REAL',     'Điểm AI (0–10, round 0.25)'),
        ('score_breakdown','TEXT',     'JSON chi tiết 10 tiêu chí'),
        ('ai_summary',     'TEXT',     'Nhận xét AI 80-100 từ'),
        ('status',         'TEXT',     'pending | passed | failed | error'),
        ('applied_at',     'TEXT',     'ISO datetime'),
    ]),
    ('interviews', 'Mỗi buổi phỏng vấn AI', [
        ('id',          'TEXT PK', 'IV-xxxxxxxxxx'),
        ('candidate_id','TEXT FK', 'Tham chiếu candidates.id'),
        ('position_id', 'TEXT',   'Vị trí phỏng vấn'),
        ('cv_filename', 'TEXT',   'Tên file CV'),
        ('cv_path',     'TEXT',   'Đường dẫn CV'),
        ('status',      'TEXT',   'pending_review | reviewed | passed | failed'),
        ('submitted_at','TEXT',   'ISO datetime'),
    ]),
    ('answers', 'Câu trả lời audio từng câu hỏi', [
        ('id',              'INT PK',  'Auto increment'),
        ('interview_id',    'TEXT FK', 'Tham chiếu interviews.id'),
        ('question_number', 'TEXT',   '01 → 06'),
        ('question_type',   'TEXT',   'Technical | Soft Skill | Experience'),
        ('audio_path',      'TEXT',   'Đường dẫn file .webm'),
        ('duration_sec',    'REAL',   'Thời lượng ghi âm'),
        ('score',           'INT',    'Điểm HR chấm thủ công (0-10)'),
        ('notes',           'TEXT',   'Ghi chú của HR'),
        ('created_at',      'TEXT',   'ISO datetime'),
    ]),
    ('candidates', 'Thông tin ứng viên (từ interview submit)', [
        ('id',         'TEXT PK', 'C-xxxxxxxx'),
        ('name',       'TEXT',   'Họ tên'),
        ('email',      'TEXT',   'Email'),
        ('created_at', 'TEXT',   'ISO datetime'),
    ]),
]

for tname, tdesc, cols in schema_tables:
    add_heading(doc, f'Bảng: {tname}', 3)
    doc.add_paragraph(tdesc)
    t = doc.add_table(rows=1, cols=3)
    t.style = 'Table Grid'
    for i, h in enumerate(['Cột', 'Kiểu', 'Mô tả']):
        t.rows[0].cells[i].text = h
        t.rows[0].cells[i].paragraphs[0].runs[0].bold = True
        set_cell_bg(t.rows[0].cells[i], '374151')
        t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    for i, (col, typ, desc) in enumerate(cols):
        row = t.add_row()
        row.cells[0].text = col
        row.cells[0].paragraphs[0].runs[0].font.name = 'Courier New'
        row.cells[1].text = typ
        row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x5B,0x21,0xB6)
        row.cells[2].text = desc
        if i % 2 == 0: set_cell_bg(row.cells[0], 'F9FAFB')
    doc.add_paragraph()

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 5. API ENDPOINTS
# ══════════════════════════════════════════════════════════════
add_heading(doc, '5. API Endpoints', 1, '0051D5')

endpoints = [
    ('GET',   '/health',                        'Public',  'Kiểm tra trạng thái server'),
    ('GET',   '/jobs',                          'Public',  'Danh sách việc làm, filter ?category='),
    ('GET',   '/jobs/{job_id}',                 'Public',  'Chi tiết JD một vị trí'),
    ('POST',  '/jobs/{job_id}/apply',           'Public',  'Nộp CV ứng tuyển (multipart: name, email, phone, cv_file)'),
    ('GET',   '/interview',                     'Public',  'Serve interview.html (HTMLResponse)'),
    ('POST',  '/interview/submit',              'Public',  'Nộp kết quả phỏng vấn (position_id, app_ref, cv_file optional, 6 audio)'),
    ('GET',   '/interview/{id}',                'Public',  'Chi tiết 1 buổi phỏng vấn'),
    ('GET',   '/candidate/{id}/interviews',     'Public',  'Tất cả phỏng vấn của 1 ứng viên'),
    ('GET',   '/interviews',                    'Admin',   'Danh sách tất cả phỏng vấn, filter ?status= ?position_id='),
    ('PATCH', '/interview/{id}/review',         'Admin',   'HR chấm điểm và cập nhật status'),
    ('GET',   '/admin/applications',            'Admin',   'Danh sách CV ứng tuyển, filter ?status= ?job_id='),
    ('GET',   '/admin/applications/{id}',       'Admin',   'Chi tiết 1 hồ sơ kèm score breakdown'),
    ('GET',   '/admin/stats',                   'Admin',   'KPI: total, passed, failed, pending, avg_score'),
    ('MOUNT', '/audio/*',                       'Public',  'StaticFiles: MP3 câu hỏi phỏng vấn'),
    ('MOUNT', '/ui/*',                          'Public',  'StaticFiles: Frontend HTML/CSS/JS'),
]

t = doc.add_table(rows=1, cols=4)
t.style = 'Table Grid'
for i, h in enumerate(['Method', 'Path', 'Auth', 'Mô tả']):
    t.rows[0].cells[i].text = h
    t.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    set_cell_bg(t.rows[0].cells[i], '131B2E')
    t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)

method_colors = {
    'GET':   '16A34A', 'POST':  '2563EB', 'PATCH': 'D97706',
    'MOUNT': '6B7280',
}
for i, (method, path, auth, desc) in enumerate(endpoints):
    row = t.add_row()
    row.cells[0].text = method
    row.cells[0].paragraphs[0].runs[0].bold = True
    row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(method_colors.get(method, '374151'))
    row.cells[1].text = path
    row.cells[1].paragraphs[0].runs[0].font.name = 'Courier New'
    row.cells[1].paragraphs[0].runs[0].font.size = Pt(9)
    row.cells[2].text = auth
    if auth == 'Admin':
        row.cells[2].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xDC,0x26,0x26)
        row.cells[2].paragraphs[0].runs[0].bold = True
    row.cells[3].text = desc
    if i % 2 == 0:
        for c in row.cells: set_cell_bg(c, 'F9FAFB')

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 6. RUBRIC CHẤM CV
# ══════════════════════════════════════════════════════════════
add_heading(doc, '6. Rubric Chấm CV (AI Scoring)', 1, '0051D5')

doc.add_paragraph(
    'GPT-4o nhận CV text + JD của vị trí, trả về JSON điểm theo từng tiêu chí. '
    'Backend tính lại tổng từ sub-scores, làm tròn 0.25. '
    'Ngưỡng đạt: ≥ 7.5 / 10 điểm.'
)

rubric = [
    ('NHÓM 1: Kinh Nghiệm Làm Việc', '4.5đ', [
        ('Số năm kinh nghiệm (years)',      '2.0đ', 'Đủ yêu cầu=2 | 60%=1 | 30%=0.5 | <30%=0'),
        ('Tính liên quan ngành (relevance)', '1.0đ', 'Đúng ngành=1 | Liên quan=0.5 | Xa=0.25 | Không liên quan=0'),
        ('Thành tích cá nhân (achievements)','0.5đ', 'Có số liệu cụ thể=0.5 | Mô tả chung=0'),
        ('Bằng cấp (degree)',               '1.0đ', 'Đạt yêu cầu=1 | Thấp hơn 1 bậc nhưng bù kinh nghiệm=0.5 | Không đạt=0'),
        ('Chuyên ngành (major)',             '1.0đ', 'Đúng chuyên ngành=1 | Liên quan=0.5 | Không liên quan=0'),
        ('Chứng chỉ (certs)',               '0.5đ', 'Đủ chứng chỉ JD=0.5 | Một phần=0.25 | Không có=0'),
    ]),
    ('NHÓM 2: Kỹ Năng Kỹ Thuật', '1.0đ', [
        ('Kỹ năng chuyên môn (technical_skills)', '1.0đ',
         '≥90% match=1 | 70-89%=0.75 | 50-69%=0.5 | 30-49%=0.25 | <30%=0\n'
         '⚠ Thiếu must-have skill → tối đa 0.25đ'),
    ]),
    ('NHÓM 3: Kỹ Năng Mềm & Hồ Sơ', '3.0đ', [
        ('Chất lượng CV (cv_quality)',      '1.0đ', 'Cấu trúc rõ, số liệu cụ thể=0.75-1 | Thiếu metrics=0.5 | Lộn xộn=0-0.25'),
        ('Dự án & Portfolio (projects)',    '1.0đ', 'Dự án thực tế + demo=1 | Thực tế ko kết quả=0.75 | Học trường=0.5 | Liệt kê ko chi tiết=0.25 | Không có=0'),
        ('Lãnh đạo & Teamwork (leadership)','1.0đ', 'Team lead rõ ràng=1 | Mentor/nhóm nhỏ=0.75 | Đóng góp team=0.5 | Liệt kê chung=0.25 | Không có=0'),
    ]),
]

for group, total, criteria in rubric:
    p = doc.add_paragraph()
    r1 = p.add_run(group + ' ')
    r1.bold = True
    r1.font.color.rgb = RGBColor(0x00,0x51,0xD5)
    r2 = p.add_run(f'(Tổng: {total})')
    r2.font.color.rgb = RGBColor(0x6B,0x72,0x80)

    t = doc.add_table(rows=1, cols=3)
    t.style = 'Table Grid'
    for i, h in enumerate(['Tiêu chí', 'Điểm tối đa', 'Mức tính điểm']):
        t.rows[0].cells[i].text = h
        t.rows[0].cells[i].paragraphs[0].runs[0].bold = True
        set_cell_bg(t.rows[0].cells[i], '374151')
        t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    for i, (name, pts, scale) in enumerate(criteria):
        row = t.add_row()
        row.cells[0].text = name
        row.cells[0].paragraphs[0].runs[0].font.name = 'Courier New'
        row.cells[0].paragraphs[0].runs[0].font.size = Pt(9)
        row.cells[1].text = pts
        row.cells[1].paragraphs[0].runs[0].bold = True
        row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x05,0x96,0x69)
        row.cells[2].text = scale
        row.cells[2].paragraphs[0].runs[0].font.size = Pt(9)
        if i % 2 == 0:
            for c in row.cells: set_cell_bg(c, 'F0FDF4')
    doc.add_paragraph()

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 7. PHỎNG VẤN AI — CẤU TRÚC & CÂU HỎI MẪU
# ══════════════════════════════════════════════════════════════
add_heading(doc, '7. Phỏng Vấn AI — Cấu Trúc & Câu Hỏi Mẫu', 1, '0051D5')

doc.add_paragraph(
    'Buổi phỏng vấn AI gồm 6 câu hỏi chia 3 phần, mỗi câu hỏi được đọc bằng '
    'giọng AI (OpenAI TTS). Ứng viên nghe câu hỏi rồi ghi âm câu trả lời. '
    'File audio (.webm) được lưu để HR nghe lại và chấm thủ công.'
)

add_heading(doc, '7.1 Cấu trúc 6 câu hỏi', 2)

q_table = doc.add_table(rows=1, cols=4)
q_table.style = 'Table Grid'
for i, h in enumerate(['STT', 'Loại', 'Badge màu', 'Mục tiêu đánh giá']):
    q_table.rows[0].cells[i].text = h
    q_table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    set_cell_bg(q_table.rows[0].cells[i], '0051D5')
    q_table.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)

q_rows = [
    ('01', 'Technical',  'Xanh dương',  'Kiến thức kỹ thuật, lý thuyết, công nghệ'),
    ('02', 'Technical',  'Xanh dương',  'Bài toán thực tế, xử lý tình huống kỹ thuật'),
    ('03', 'Soft Skill', 'Xanh lá',     'Giao tiếp, làm việc nhóm, xử lý xung đột'),
    ('04', 'Soft Skill', 'Xanh lá',     'Tư duy giải quyết vấn đề, áp lực công việc'),
    ('05', 'Experience', 'Vàng amber',  'Dự án đã làm, vai trò, kết quả cụ thể'),
    ('06', 'Experience', 'Vàng amber',  'Thất bại/bài học, định hướng phát triển'),
]
q_colors = {'Technical': 'EFF6FF', 'Soft Skill': 'ECFDF5', 'Experience': 'FFFBEB'}
for stt, qtype, badge, goal in q_rows:
    row = q_table.add_row()
    row.cells[0].text = f'Câu {stt}'
    row.cells[0].paragraphs[0].runs[0].bold = True
    row.cells[1].text = qtype
    row.cells[1].paragraphs[0].runs[0].bold = True
    row.cells[2].text = badge
    row.cells[3].text = goal
    for c in row.cells: set_cell_bg(c, q_colors[qtype])

doc.add_paragraph()

add_heading(doc, '7.2 Câu hỏi mẫu — Backend Developer', 2)

sample_questions = [
    ('01', 'Technical',
     'Bạn hãy giải thích sự khác biệt giữa REST API và GraphQL. '
     'Trong dự án của bạn, khi nào bạn sẽ chọn GraphQL thay vì REST?'),
    ('02', 'Technical',
     'Hệ thống của bạn đang xử lý 10.000 request/giây và bắt đầu chậm lại. '
     'Bạn sẽ debug và tối ưu như thế nào? Nêu ít nhất 3 bước cụ thể.'),
    ('03', 'Soft Skill',
     'Kể về một lần bạn không đồng ý với quyết định kỹ thuật của team lead. '
     'Bạn đã xử lý tình huống đó như thế nào?'),
    ('04', 'Soft Skill',
     'Bạn nhận được task deadline gấp 2 ngày nhưng scope quá lớn. '
     'Bạn sẽ ưu tiên và communicate với stakeholder như thế nào?'),
    ('05', 'Experience',
     'Mô tả một dự án backend bạn tự hào nhất: tech stack, vấn đề bạn giải quyết '
     'và kết quả đo lường được (performance, scale, user impact).'),
    ('06', 'Experience',
     'Kể về một bug production nghiêm trọng bạn từng gây ra hoặc xử lý. '
     'Bài học bạn rút ra là gì và bạn đã thay đổi workflow như thế nào?'),
]

for stt, qtype, question in sample_questions:
    p = doc.add_paragraph()
    badge_colors = {'Technical': RGBColor(0x1D,0x4E,0xD8), 'Soft Skill': RGBColor(0x05,0x96,0x69), 'Experience': RGBColor(0xB4,0x5A,0x09)}
    r_num = p.add_run(f'Câu {stt} [{qtype}]  ')
    r_num.bold = True
    r_num.font.color.rgb = badge_colors[qtype]
    p.add_run(question)

doc.add_paragraph()

add_heading(doc, '7.3 Câu hỏi mẫu — AI/ML Engineer', 2)

aiml_questions = [
    ('01', 'Technical',
     'Giải thích sự khác nhau giữa overfitting và underfitting. '
     'Bạn phát hiện và xử lý hai vấn đề này bằng kỹ thuật nào?'),
    ('02', 'Technical',
     'Bạn cần deploy một model NLP xử lý 1000 request/phút với latency < 200ms. '
     'Bạn sẽ thiết kế pipeline serving như thế nào?'),
    ('03', 'Soft Skill',
     'Làm thế nào bạn giải thích kết quả của một mô hình ML phức tạp '
     'cho một stakeholder không có background kỹ thuật?'),
    ('04', 'Soft Skill',
     'Bạn và data engineer có quan điểm khác nhau về cách xử lý missing data. '
     'Bạn tiếp cận và đạt đồng thuận như thế nào?'),
    ('05', 'Experience',
     'Mô tả một bài toán ML bạn đã giải quyết end-to-end: '
     'từ data collection, feature engineering, modeling đến monitoring production.'),
    ('06', 'Experience',
     'Kể về một experiment ML thất bại. Nguyên nhân là gì? '
     'Bạn đã thay đổi approach như thế nào và học được gì?'),
]

for stt, qtype, question in aiml_questions:
    p = doc.add_paragraph()
    badge_colors = {'Technical': RGBColor(0x1D,0x4E,0xD8), 'Soft Skill': RGBColor(0x05,0x96,0x69), 'Experience': RGBColor(0xB4,0x5A,0x09)}
    r_num = p.add_run(f'Câu {stt} [{qtype}]  ')
    r_num.bold = True
    r_num.font.color.rgb = badge_colors[qtype]
    p.add_run(question)

add_heading(doc, '7.4 Tên file audio câu hỏi (naming convention)', 2)
doc.add_paragraph(
    'File audio được đặt tên theo pattern: '
)
p = doc.add_paragraph()
r = p.add_run('Junior_[PositionID]_[N]_[Type].mp3')
r.font.name = 'Courier New'
r.font.size = Pt(11)
r.bold = True
doc.add_paragraph('Ví dụ:')
examples = [
    'Junior_Backend_Developer_01_Technical.mp3',
    'Junior_Backend_Developer_03_Soft Skill.mp3',
    'Junior_AIML_Engineer_05_Experience.mp3',
    'intro.mp3  ← Intro chung cho tất cả buổi phỏng vấn',
]
for ex in examples:
    p = doc.add_paragraph(style='List Bullet')
    r = p.add_run(ex)
    r.font.name = 'Courier New'
    r.font.size = Pt(9)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 8. EMAIL TEMPLATES
# ══════════════════════════════════════════════════════════════
add_heading(doc, '8. Email Templates', 1, '0051D5')

add_heading(doc, '8.1 Email Mời Phỏng Vấn (Passed)', 2)
pass_email = [
    ('Subject',   'Mời phỏng vấn vị trí [JOB_TITLE] tại PAI HR'),
    ('Sender',    'agentanalysisfeedback@gmail.com'),
    ('Nội dung',  '✓ Chúc mừng đạt vòng sơ loại CV\n✓ Link phỏng vấn AI online (10-15 phút)\n✓ Hạn link: 7 ngày\n✓ Nút CTA: "Bắt đầu phỏng vấn →"\n✗ KHÔNG hiển thị điểm số'),
    ('Link format','https://[IP]:8000/interview?ref=APP-xxx&pos=Junior_[JOB_ID]'),
]
for key, val in pass_email:
    p = doc.add_paragraph()
    p.add_run(key + ': ').bold = True
    p.add_run(val)

add_heading(doc, '8.2 Email Từ Chối (Failed)', 2)
fail_email = [
    ('Subject',  'Kết quả hồ sơ ứng tuyển vị trí [JOB_TITLE] tại PAI HR'),
    ('Nội dung', '✓ Cảm ơn thời gian ứng tuyển\n✓ Thông báo chưa phù hợp lần này\n✓ Khuyến khích ứng tuyển tương lai\n✗ KHÔNG nêu lý do cụ thể\n✗ KHÔNG hiển thị điểm số'),
]
for key, val in fail_email:
    p = doc.add_paragraph()
    p.add_run(key + ': ').bold = True
    p.add_run(val)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════
# 9. CẤU HÌNH & TRIỂN KHAI
# ══════════════════════════════════════════════════════════════
add_heading(doc, '9. Cấu Hình & Triển Khai', 1, '0051D5')

add_heading(doc, '9.1 Biến môi trường (.env)', 2)
env_vars = [
    ('OPENAI_API_KEY', 'Required', 'API key OpenAI cho GPT-4o và TTS'),
    ('ADMIN_KEY',      'Required', 'Mật khẩu đăng nhập admin UI (VD: admin@2024)'),
    ('SMTP_HOST',      'Required', 'SMTP server (smtp.gmail.com)'),
    ('SMTP_PORT',      'Required', '587 (TLS)'),
    ('SMTP_USER',      'Required', 'Gmail address gửi mail'),
    ('SMTP_PASS',      'Required', 'Gmail App Password (16 ký tự)'),
    ('INTERVIEW_URL',  'Required', 'Base URL trang phỏng vấn (https://[IP]:8000/interview)'),
]
t = doc.add_table(rows=1, cols=3)
t.style = 'Table Grid'
for i, h in enumerate(['Biến', 'Bắt buộc', 'Mô tả']):
    t.rows[0].cells[i].text = h
    t.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    set_cell_bg(t.rows[0].cells[i], '374151')
    t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
for i, (var, req, desc) in enumerate(env_vars):
    row = t.add_row()
    row.cells[0].text = var
    row.cells[0].paragraphs[0].runs[0].font.name = 'Courier New'
    row.cells[0].paragraphs[0].runs[0].font.size = Pt(9)
    row.cells[1].text = req
    row.cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xDC,0x26,0x26)
    row.cells[2].text = desc
    if i % 2 == 0:
        for c in row.cells: set_cell_bg(c, 'F9FAFB')

add_heading(doc, '9.2 Lệnh khởi động', 2)
cmds = [
    ('Backend (HTTPS)',  'python3 -m uvicorn backend.interview_api:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem'),
    ('Frontend',         'Được serve qua /ui/ endpoint của backend (không cần server riêng)'),
    ('Tạo SSL cert',     'mkcert 10.6.x.x localhost 127.0.0.1'),
    ('Cài mkcert CA',    'mkcert -install  (cần sudo, tin tưởng cert trên thiết bị)'),
]
for label, cmd in cmds:
    p = doc.add_paragraph()
    p.add_run(label + ':\n').bold = True
    r = p.add_run('  ' + cmd)
    r.font.name = 'Courier New'
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x05,0x96,0x69)

add_heading(doc, '9.3 URLs truy cập', 2)
urls = [
    ('Admin UI',            'https://[IP]:8000/ui/ats_ui.html'),
    ('Trang phỏng vấn',     'https://[IP]:8000/interview?ref=[APP_ID]&pos=[JOB_ID]'),
    ('API Health check',    'https://[IP]:8000/health'),
    ('Docs tự động (dev)',  'https://[IP]:8000/docs'),
]
for label, url in urls:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(label + ': ').bold = True
    r = p.add_run(url)
    r.font.name = 'Courier New'
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x1D,0x4E,0xD8)

# Footer note
doc.add_paragraph()
note = doc.add_paragraph()
note.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = note.add_run('── PAI HR Internal Document · Confidential ──')
r.font.color.rgb = RGBColor(0x9C,0xA3,0xAF)
r.font.size = Pt(9)

# ── Save ──────────────────────────────────────────────────────
out = '/Users/_qh.fol_/ats_phongvan/PAI_HR_Project_Documentation.docx'
doc.save(out)
print(f'Saved: {out}')
