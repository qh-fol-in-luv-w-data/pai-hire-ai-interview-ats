import { Link } from 'react-router-dom';
import { Card } from '../../shared/ui';

const endpoints = [
  ['POST', '/api/v1/score-cv', 'Đẩy CV và JD để chấm điểm, trích xuất thông tin và tạo app_id.'],
  ['POST', '/api/v1/schedule', 'Tạo link phỏng vấn theo khung thời gian từ app_id.'],
  ['POST', '/api/v1/schedule-with-cv', 'Đẩy CV, tạo câu hỏi và cấp lịch phỏng vấn trong một lần gọi.'],
  ['GET', '/api/v1/report/{app_id}', 'Lấy trạng thái và báo cáo của hồ sơ thuộc công ty bạn.'],
  ['GET', '/api/v1/applications/{app_id}/basic', 'Lấy thông tin cơ bản của một hồ sơ thuộc công ty bạn.'],
  ['GET', '/api/v1/slot/{token}/validate', 'Kiểm tra link phỏng vấn; chỉ dùng bởi trang phỏng vấn.'],
];

const scoreCurl = `curl -sS -X POST "https://hire.ctpai.vn/api/v1/score-cv" \\
  -H "Authorization: Bearer $PAI_API_KEY" \\
  -F "cv_file=@./ung-vien.pdf" \\
  -F "jd_text=Mô tả công việc và yêu cầu vị trí..." \\
  -F "candidate_name=Nguyen Van A" \\
  -F "candidate_email=a@example.com" \\
  -F "level=Junior"`;

const scheduleCurl = `curl -sS -X POST "https://hire.ctpai.vn/api/v1/schedule" \\
  -H "Authorization: Bearer $PAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"app_id":"APP-XXXXXXXX","start_time":"2026-08-12T09:00:00+07:00","end_time":"2026-08-12T10:00:00+07:00","level":"Junior"}'`;

export function EnterprisePage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/apply" className="font-extrabold text-navy-950">PAI Hire</Link>
          <Link to="/apply" className="text-sm font-bold text-brand-700">← Quay lại trang tìm việc</Link>
        </div>
      </header>

      <section className="hero-mesh text-white">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
          <p className="text-xs font-extrabold uppercase tracking-[.2em] text-blue-200">CTPAI · Tuyển dụng thông minh</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-extrabold tracking-tight sm:text-5xl">Tích hợp AI tuyển dụng vào hệ thống của doanh nghiệp.</h1>
          <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-300">Doanh nghiệp mới có thể đăng ký tài khoản để CTPAI xét duyệt. Sau khi được duyệt, đăng nhập để quản lý API key, mua thêm lượt chấm CV/lịch phỏng vấn và theo dõi mức sử dụng.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link className="btn-primary bg-brand-500 !text-white shadow-lg shadow-blue-950/30 hover:!bg-brand-600" to="/enterprise/portal">Đăng nhập tài khoản doanh nghiệp</Link>
            <Link className="btn-secondary border-white/40 bg-white/15 !text-white hover:!bg-white/25" to="/enterprise/register">Đăng ký tài khoản doanh nghiệp</Link>
            <a className="btn-secondary border-white/25 bg-white/10 !text-white hover:!bg-white/20" href="#api">Xem tài liệu API</a>
          </div>
        </div>
      </section>

      <div id="api" className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
        <Card className="p-6">
          <h2 className="section-title">Xác thực</h2>
          <p className="muted mt-2">Mọi API dữ liệu dùng header bên dưới. Không đặt API key trong frontend, Git hoặc ảnh chụp màn hình.</p>
          <pre className="mt-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm text-emerald-300"><code>Authorization: Bearer $PAI_API_KEY</code></pre>
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          {endpoints.map(([method, path, description]) => (
            <Card key={path} className="p-5">
              <div className="flex items-center gap-3">
                <span className={method === 'GET' ? 'rounded-lg bg-blue-50 px-2 py-1 text-xs font-extrabold text-blue-700' : 'rounded-lg bg-emerald-50 px-2 py-1 text-xs font-extrabold text-emerald-700'}>{method}</span>
                <code className="text-sm font-bold text-slate-800">{path}</code>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{description}</p>
            </Card>
          ))}
        </div>
        <Card className="p-6">
          <h2 className="section-title">Ví dụ: đẩy CV để chấm</h2>
          <pre className="mt-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100"><code>{scoreCurl}</code></pre>
        </Card>
        <Card className="p-6">
          <h2 className="section-title">Ví dụ: tạo lịch phỏng vấn</h2>
          <pre className="mt-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100"><code>{scheduleCurl}</code></pre>
        </Card>
        <Card className="border-blue-200 p-6">
          <h2 className="section-title">Cấp API key</h2>
          <p className="muted mt-2">Doanh nghiệp đăng ký sử dụng dịch vụ, sau đó quản trị CTPAI duyệt tài khoản. Khi được duyệt, doanh nghiệp có khu vực riêng để tự tạo/đổi API key; mỗi key chỉ được hiển thị một lần.</p>
          <Link className="btn-primary mt-5 inline-flex" to="/enterprise/register">Điền form xin tài khoản</Link>
        </Card>
      </div>
    </main>
  );
}
