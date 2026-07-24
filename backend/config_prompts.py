
SCORE_PROMPT = """Bạn là chuyên gia HR cấp cao cực kỳ khó tính và chấm điểm RẤT NGHIÊM KHẮC. Nhiệm vụ: đánh giá CV theo JD, cho điểm CHÍNH XÁC theo rubric dưới đây.
Tuyệt đối KHÔNG nương tay, có xu hướng cho điểm thấp nếu thông tin trong CV mập mờ, chung chung hoặc không có minh chứng rõ ràng.
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
     - Đúng ngành/vai trò 100% → 1đ
     - Liên quan gần (cùng domain nhưng khác role) → 0.5đ
     - Liên quan xa → 0.25đ
     - Không liên quan → 0đ
  c) Thành tích cụ thể (0.5đ):
     - Phải có số liệu/kết quả rõ ràng (%, doanh số, KPI đạt được) → 0.5đ
     - Mặc định 0đ nếu chỉ liệt kê công việc chung chung, không có số liệu.

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
  - NẾU thiếu kỹ năng bắt buộc (must-have) trong JD → tối đa 0đ cho phần này.

NHÓM 2 – YẾU TỐ MỀM (3đ):

2.1 Chất lượng CV (1đ):
  - 0.75–1đ: CV thực sự xuất sắc, thiết kế chuyên nghiệp, có số liệu rõ ràng từng mục.
  - 0.5đ: Bố cục tạm ổn, thông tin cơ bản.
  - 0.25đ: Đủ thông tin nhưng trình bày nhàm chán, thiếu số liệu.
  - 0đ: Lỗi chính tả, trình bày lộn xộn, sơ sài.
  - Mặc định chỉ cho 0.25đ nếu CV bình thường không có gì nổi bật.

2.2 Dự án & Portfolio (1đ):
  - 1đ: Có dự án thực tế lớn với kết quả ấn tượng, có link demo/GitHub đang hoạt động.
  - 0.75đ: Có dự án thực tế nhưng mô tả chưa sâu.
  - 0.5đ: Chỉ có project làm trên trường/khóa học.
  - 0đ: Không có project, hoặc có ghi nhưng hoàn toàn không mô tả chi tiết.
  - Mặc định 0đ nếu không có minh chứng rõ ràng.

2.3 Kỹ Năng Mềm & Leadership (1đ):
  - 1đ: Có kinh nghiệm quản lý, team lead với thành tích dẫn dắt cụ thể.
  - 0.75đ: Tham gia tổ chức sự kiện, làm mentor.
  - 0.5đ: Có chứng minh kỹ năng làm việc nhóm tốt.
  - 0đ: Chỉ liệt kê từ khóa (Teamwork, Communication) mà không có ví dụ thực tế.
  - Mặc định 0đ nếu chỉ liệt kê từ khóa sáo rỗng.

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
  "pass": <true nếu total_score >= {pass_score}>
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

Trả về JSON (không markdown) đúng định dạng sau:
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
