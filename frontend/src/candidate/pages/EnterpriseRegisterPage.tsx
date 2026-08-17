import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, jsonInit } from '../../shared/api';
import { Button, Card } from '../../shared/ui';

export function EnterpriseRegisterPage() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await api<{message:string}>('/api/enterprise/register', jsonInit('POST', data));
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể gửi yêu cầu đăng ký');
    }
  };
  return <main className="page-container"><div className="mx-auto max-w-2xl">
    <Link to="/enterprise" className="text-sm font-bold text-brand-700">← Quay lại tài liệu API</Link>
    <Card className="mt-5 p-6 sm:p-8"><p className="eyebrow">Dành cho doanh nghiệp</p><h1 className="section-title mt-2">Đăng ký sử dụng API tuyển dụng</h1><p className="muted mt-2">Gửi thông tin liên hệ. CTPAI duyệt yêu cầu trước khi cấp API key.</p>
      {message ? <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><p className="font-extrabold text-emerald-800">Đã gửi yêu cầu</p><p className="mt-2 text-sm leading-6 text-emerald-700">{message}</p></div> : <form className="mt-7 space-y-7" onSubmit={submit}>
        <section><h2 className="font-extrabold text-slate-950">Thông tin doanh nghiệp</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="sm:col-span-2"><span className="label">Tên doanh nghiệp</span><input className="field" name="company_name" placeholder="Ví dụ: Công ty TNHH ABC" required/></label>
          <label><span className="label">Mã số thuế</span><input className="field" name="tax_code" placeholder="Nhập mã số thuế" inputMode="numeric" required/></label>
          <label><span className="label">Quy mô nhân sự</span><select className="field" name="company_size" defaultValue="" required><option value="" disabled>Chọn quy mô</option><option>1–50 nhân sự</option><option>51–200 nhân sự</option><option>201–500 nhân sự</option><option>501–1.000 nhân sự</option><option>Trên 1.000 nhân sự</option></select></label>
        </div></section>
        <section><h2 className="font-extrabold text-slate-950">Thông tin liên hệ</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label><span className="label">Email</span><input className="field" name="email" type="email" placeholder="contact@congty.vn" required/></label>
          <label><span className="label">Số điện thoại</span><input className="field" name="phone" type="tel" placeholder="0901 234 567" required/></label>
          <label className="sm:col-span-2"><span className="label">Mật khẩu tài khoản doanh nghiệp</span><input className="field" name="password" type="password" minLength={10} placeholder="Tối thiểu 10 ký tự" required autoComplete="new-password"/><span className="mt-1 block text-xs text-slate-500">Tài khoản doanh nghiệp độc lập với tài khoản ứng viên. Có thể dùng cùng email, nhưng mật khẩu và dữ liệu quản lý hoàn toàn riêng.</span></label>
        </div></section>
        {error&&<p className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
        <Button className="w-full">Gửi yêu cầu đăng ký</Button>
      </form>}
    </Card>
  </div></main>;
}
