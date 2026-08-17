import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Menu, Search } from 'lucide-react';
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import type { Application, Interview, Job, PrepQuestion } from '../shared/types';
import { adminApi, api, jsonInit } from '../shared/api';
import { Badge, Button, Card, Dialog, Drawer, Empty, ErrorState, Loading, SelectField } from '../shared/ui';
import { statusLabel, statusTone } from '../shared/status';
import { cn, formatDate, levelName, positionName, uniquePositions } from '../shared/utils';
import { composeJd, emptyJd, parseJd, type JdSections } from './jd';
import { InterviewDrawerPro } from './InterviewDrawerPro';
import { IntegrationsPage } from './IntegrationsPage';
import { ApiApplicationsPage } from './ApiApplicationsPage';
import { AccountsPage } from './AccountsPage';
import { RichTextEditor } from '../shared/RichTextEditor';

type Stats = { total: number; passed: number; failed: number; pending: number; pending_approval: number; avg_score: number | null; submitted_interviews?: number; evaluated_interviews?: number; new_applications?: number };
type FeedbackStat = { position_id: string; count: number; avg_nps: number | null; avg_ratings: Record<string, number> };
type LoginResponse = { token: string; user: { id?:string; name: string; role: string; email?:string; phone?:string } };
const salaryOptions=[
  {value:'AUTO',label:'Tự động theo vị trí và cấp bậc'},
  {value:'8–12 triệu VNĐ/tháng (Gross)',label:'8–12 triệu/tháng'},
  {value:'12–18 triệu VNĐ/tháng (Gross)',label:'12–18 triệu/tháng'},
  {value:'18–25 triệu VNĐ/tháng (Gross)',label:'18–25 triệu/tháng'},
  {value:'25–35 triệu VNĐ/tháng (Gross)',label:'25–35 triệu/tháng'},
  {value:'35–50 triệu VNĐ/tháng (Gross)',label:'35–50 triệu/tháng'},
  {value:'50–80 triệu VNĐ/tháng (Gross)',label:'50–80 triệu/tháng'},
  {value:'80–120 triệu VNĐ/tháng (Gross)',label:'80–120 triệu/tháng'},
];

const pageMeta: Record<string, [string, string]> = {
  '/admin/ui/dashboard': ['Tổng quan', 'Theo dõi toàn bộ quy trình tuyển dụng'],
  '/admin/ui/applications': ['Hồ sơ ứng viên', 'Duyệt CV, chuẩn bị câu hỏi và gửi lịch phỏng vấn'],
  '/admin/ui/pipeline': ['Pipeline tuyển dụng', 'Theo dõi ứng viên theo từng giai đoạn xử lý'],
  '/admin/ui/interviews': ['Bài phỏng vấn', 'Đánh giá câu trả lời và quyết định kết quả'],
  '/admin/ui/feedback': ['Trải nghiệm ứng viên', 'Phản hồi và chỉ số hài lòng sau phỏng vấn'],
  '/admin/ui/jobs': ['Vị trí tuyển dụng', 'Quản lý mô tả và yêu cầu công việc'],
  '/admin/ui/settings': ['Thiết lập hệ thống', 'Cấu hình chấm CV và vận hành tuyển dụng'],
  '/admin/ui/integrations': ['Tích hợp API', 'Cấp cấu hình API an toàn cho từng công ty'],
  '/admin/ui/api-applications': ['Hồ sơ gọi API', 'Theo dõi hồ sơ theo từng doanh nghiệp tích hợp'],
  '/admin/ui/accounts': ['Tài khoản & phân quyền', 'Cấp và thu hồi quyền quản trị'],
};
const adminPositionName = (position?: string, source?: string) => source === 'api'||/^jd[_\s-]/i.test((position||'').trim())||position==='-' ? '-' : positionName(position || '');
const cvScoreLabel = (score?: number | null) => score == null || !Number.isFinite(Number(score)) ? '—' : `${Number(score).toFixed(1)}/5`;

function Login() {
  const navigate = useNavigate();
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () => api<LoginResponse>('/auth/login', jsonInit('POST', { account, password })),
    onSuccess: (data) => {
      if (!['admin','platform_admin'].includes(data.user?.role || '')) throw new Error('Tài khoản không có quyền quản trị');
      localStorage.setItem('pai_admin_key', data.token);
      localStorage.setItem('pai_admin_name', data.user.name || 'Quản trị viên');
      localStorage.setItem('pai_candidate_user',JSON.stringify(data.user));
      localStorage.setItem('pai_candidate_token',data.token);
      navigate('/admin/ui/dashboard', { replace: true });
    },
  });
  return <main className="grid min-h-screen place-items-center p-4">
    <Card className="grid w-full max-w-4xl overflow-hidden md:grid-cols-[1.05fr_.95fr]">
      <section className="hidden bg-navy-950 p-10 text-white md:flex md:flex-col md:justify-between">
        <div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-blue-300">Hệ thống nội bộ</p><h1 className="mt-8 text-3xl font-extrabold tracking-tight">PAI Hire</h1><p className="mt-3 max-w-sm leading-7 text-slate-300">Không gian quản trị tuyển dụng tập trung, rõ ràng và an toàn.</p></div>
        <p className="text-xs text-slate-500">Dành riêng cho đội ngũ tuyển dụng</p>
      </section>
      <form className="p-7 sm:p-10" onSubmit={(event) => { event.preventDefault(); login.mutate(); }}>
        <p className="text-sm font-bold text-brand-700">CỔNG QUẢN TRỊ</p><h2 className="mt-2 text-2xl font-extrabold">Đăng nhập hệ thống</h2><p className="mt-2 text-sm text-slate-500">Nhập tài khoản được cấp để tiếp tục.</p>
        <label className="mt-7 block"><span className="label">Email hoặc tài khoản</span><input className="field" value={account} onChange={(e) => setAccount(e.target.value)} autoComplete="username" required /></label>
        <label className="mt-4 block"><span className="label">Mật khẩu</span><input className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <a className="mt-3 inline-block text-sm font-bold text-brand-700 hover:underline" href={`/reset-password?type=user${account?'&email='+encodeURIComponent(account):''}`}>Quên mật khẩu?</a>
        {login.error && <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{login.error.message}</p>}
        <Button className="mt-6 w-full" disabled={login.isPending}>{login.isPending ? 'Đang xác thực...' : 'Đăng nhập'}</Button>
      </form>
    </Card>
  </main>;
}

const nav = [
  {href:'/admin/ui/dashboard',label:'Tổng quan',note:'Số liệu tuyển dụng'},
  {href:'/admin/ui/applications',label:'Hồ sơ ứng viên',note:'Duyệt và xử lý CV'},
  {href:'/admin/ui/pipeline',label:'Pipeline',note:'Luồng tuyển dụng'},
  {href:'/admin/ui/interviews',label:'Bài phỏng vấn',note:'Xem và đánh giá'},
  {href:'/admin/ui/feedback',label:'Phản hồi',note:'Trải nghiệm ứng viên'},
  {href:'/admin/ui/jobs',label:'Vị trí tuyển dụng',note:'Việc làm và JD'},
  {href:'/admin/ui/settings',label:'Thiết lập',note:'Cấu hình hệ thống'},
  {href:'/admin/ui/integrations',label:'Tích hợp API',note:'Công ty và API key'},
  {href:'/admin/ui/api-applications',label:'Hồ sơ gọi API',note:'Hồ sơ theo doanh nghiệp'},
  {href:'/admin/ui/accounts',label:'Tài khoản & quyền',note:'Cấp quyền quản trị'},
] as const;

function Shell() {
  const location = useLocation(); const navigate = useNavigate(); const [menu, setMenu] = useState(false); const [accountMenu,setAccountMenu]=useState(false);
  const [title, subtitle] = pageMeta[location.pathname] || pageMeta['/admin/ui/dashboard'];
  const logout=()=>{localStorage.removeItem('pai_admin_key');sessionStorage.removeItem('pai_admin_key');navigate('/admin/login')};
  const sidebar=<>
    <div className="px-5 pb-5 pt-6">
      <div className="flex items-center gap-3">
        <div><p className="text-base font-extrabold tracking-tight">PAI Tuyển dụng</p><p className="mt-0.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Trung tâm quản trị</p></div>
      </div>
    </div>
    <div className="mx-4 h-px bg-slate-800"/>
    <div className="px-5 pb-2 pt-6 text-[10px] font-extrabold uppercase tracking-[.18em] text-slate-500">Điều hướng</div>
    <nav className="flex-1 space-y-1.5 overflow-y-auto px-3 pb-4">
      {nav.map(({href,label,note})=><NavLink key={href} to={href} onClick={()=>setMenu(false)} className={({isActive})=>cn('group block rounded-2xl border-l-2 px-4 py-3 transition',isActive?'border-blue-500 bg-white text-navy-950 shadow-lg shadow-black/10':'border-transparent text-slate-300 hover:bg-slate-800/80 hover:text-white')}>
        {({isActive})=><span className="min-w-0"><span className="block text-sm font-extrabold">{label}</span><span className={cn('mt-0.5 block truncate text-[11px] font-medium',isActive?'text-slate-500':'text-slate-500')}>{note}</span></span>}
      </NavLink>)}
    </nav>
    <div className="border-t border-slate-800 p-3">
      <div className="rounded-2xl bg-slate-900 p-3">
        <div className="flex items-center gap-3"><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{localStorage.getItem('pai_admin_name')||'Quản trị viên'}</p><p className="text-[11px] text-slate-500">Tài khoản quản trị</p></div><button className="rounded-lg px-2 py-1 text-xs font-bold text-slate-400 hover:bg-slate-800 hover:text-white" onClick={logout}>Đăng xuất</button></div>
      </div>
    </div>
  </>;
  return <div className="min-h-screen lg:pl-72">
    <aside className="fixed inset-y-0 left-0 z-50 hidden w-72 flex-col bg-navy-950 text-white shadow-2xl lg:flex">{sidebar}</aside>
    {menu&&<div className="fixed inset-0 z-50 lg:hidden"><button className="absolute inset-0 bg-slate-950/50" onClick={()=>setMenu(false)}/><aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-navy-950 text-white">{sidebar}</aside></div>}
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur"><div className="flex h-20 items-center gap-4 px-4 sm:px-6 lg:px-8"><button className="icon-btn lg:hidden" onClick={()=>setMenu(true)}><Menu/></button><div className="min-w-0 flex-1"><h1 className="truncate text-xl font-extrabold">{title}</h1><p className="hidden truncate text-sm text-slate-500 sm:block">{subtitle}</p></div><div className="relative hidden sm:block" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setAccountMenu(false)}}><button type="button" onClick={()=>setAccountMenu(!accountMenu)} className={cn('flex items-center gap-2 rounded-2xl border bg-white px-3 py-2.5 shadow-sm transition',accountMenu?'border-blue-300 ring-4 ring-blue-100':'border-slate-200')}><span className="text-sm font-bold">{localStorage.getItem('pai_admin_name')||'Quản trị viên'}</span><span className="text-xs text-slate-400">{accountMenu?'Đóng':'Mở'}</span></button>{accountMenu&&<div className="select-menu absolute right-0 top-full mt-2 w-64 rounded-[20px] border border-slate-200 bg-white p-2 shadow-[0_22px_60px_rgba(7,20,38,.2)]"><button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50" onClick={()=>{navigate('/admin/ui/dashboard');setAccountMenu(false)}}><span className="text-sm font-bold">Tổng quan quản trị</span></button><button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50" onClick={()=>{navigate('/admin/ui/applications');setAccountMenu(false)}}><span className="text-sm font-bold">Hồ sơ ứng viên</span></button><button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50" onClick={()=>window.location.href='/candidate/history?tab=profile'}><span className="text-sm font-bold">Hồ sơ tài khoản</span></button><div className="my-1 border-t border-slate-100"/><button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-red-600 hover:bg-red-50" onClick={logout}><span className="text-sm font-bold">Đăng xuất</span></button></div>}</div></div></header>
    <div className="page-container"><Routes><Route path="/admin/ui/dashboard" element={<Dashboard/>}/><Route path="/admin/ui/applications" element={<Applications/>}/><Route path="/admin/ui/pipeline" element={<Pipeline/>}/><Route path="/admin/ui/interviews" element={<Interviews/>}/><Route path="/admin/ui/feedback" element={<Feedback/>}/><Route path="/admin/ui/jobs" element={<Jobs/>}/><Route path="/admin/ui/settings" element={<SystemSettings/>}/><Route path="/admin/ui/integrations" element={<IntegrationsPage/>}/><Route path="/admin/ui/api-applications" element={<ApiApplicationsPage/>}/><Route path="/admin/ui/accounts" element={<AccountsPage/>}/><Route path="*" element={<Navigate to="/admin/ui/dashboard" replace/>}/></Routes></div>
  </div>;
}

function Dashboard() {
  const stats=useQuery({queryKey:['admin-stats'],queryFn:()=>adminApi<Stats>('/admin/stats')});
  const apps=useQuery({queryKey:['applications'],queryFn:()=>adminApi<{applications:Application[]}>('/admin/applications?limit=8')});
  if(stats.isLoading)return <Loading/>; if(stats.error)return <ErrorState message={stats.error.message} retry={()=>stats.refetch()}/>;
  const total=stats.data?.total||0;
  const pipeline=[
    {label:'Chờ xử lý',value:(stats.data?.pending||0)+(stats.data?.pending_approval||0),color:'bg-amber-400'},
    {label:'Đã gửi phỏng vấn',value:stats.data?.passed||0,color:'bg-emerald-400'},
    {label:'Không đạt',value:stats.data?.failed||0,color:'bg-rose-400'},
  ];
  const metrics=[
    {label:'Tổng hồ sơ',value:total,caption:'Toàn bộ ứng viên',glow:'#dbeafe'},
    {label:'Chờ HR duyệt',value:stats.data?.pending_approval||0,caption:'Cần xử lý hôm nay',glow:'#fef3c7'},
    {label:'Đã gửi phỏng vấn',value:stats.data?.passed||0,caption:'Đang trong quy trình',glow:'#d1fae5'},
    {label:'Điểm CV trung bình',value:stats.data?.avg_score==null?'—':Number(stats.data.avg_score).toFixed(1),caption:'Thang điểm 5',glow:'#ede9fe'},
  ];
  return <div className="space-y-6">
    <section className="hero-mesh rounded-[30px] p-6 text-white shadow-[0_24px_65px_rgba(7,20,38,.24)] sm:p-8"><div className="relative z-10 flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between"><div className="max-w-2xl"><p className="text-[10px] font-extrabold uppercase tracking-[.24em] text-blue-200">Trung tâm điều hành tuyển dụng</p><h2 className="mt-3 text-3xl font-extrabold tracking-[-.04em] sm:text-4xl">Chào buổi làm việc, {localStorage.getItem('pai_admin_name')||'Quản trị viên'}</h2><p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">Nắm bắt toàn bộ pipeline, ưu tiên hồ sơ cần xử lý và ra quyết định nhanh hơn từ một màn hình.</p></div><div className="glass-dark grid min-w-[290px] grid-cols-2 gap-4 rounded-[22px] p-4"><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Hệ thống</p><p className="mt-2 flex items-center gap-2 text-sm font-extrabold"><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_#34d399]"/>Đang vận hành</p></div><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Cần chú ý</p><p className="mt-2 text-xl font-extrabold">{stats.data?.pending_approval||0} <span className="text-xs text-slate-400">hồ sơ</span></p></div></div></div></section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{metrics.map(({label,value,caption,glow})=><article key={label} className="metric-card" style={{'--metric-glow':glow} as CSSProperties}><div className="relative z-10 flex items-start justify-between"><div><p className="text-xs font-extrabold uppercase tracking-[.08em] text-slate-500">{label}</p><p className="mt-3 text-3xl font-extrabold tracking-tight text-navy-950">{value}</p><p className="mt-2 text-xs font-semibold text-slate-400">{caption}</p></div></div></article>)}</section>
    <Card className="p-5 sm:p-6"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Thông báo cần xử lý</p><h2 className="section-title mt-2">Đếm theo từng nhóm</h2></div><p className="text-xs font-semibold text-slate-400">Cập nhật theo dữ liệu mới nhất</p></div><div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><NavLink to="/admin/ui/applications?status=pending" className="rounded-2xl border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-300 hover:bg-blue-50"><p className="text-xs font-bold text-slate-500">Hồ sơ mới</p><p className="mt-2 text-2xl font-extrabold text-navy-950">{stats.data?.new_applications || 0}</p><p className="mt-1 text-xs font-semibold text-slate-400">Chờ xử lý</p></NavLink><NavLink to="/admin/ui/applications?status=pending_hr_approval_passed" className="rounded-2xl border border-amber-200 bg-amber-50 p-4 transition hover:border-amber-300"><p className="text-xs font-bold text-amber-700">Chờ gửi link</p><p className="mt-2 text-2xl font-extrabold text-amber-900">{stats.data?.pending_approval || 0}</p><p className="mt-1 text-xs font-semibold text-amber-700/70">HR cần duyệt</p></NavLink><NavLink to="/admin/ui/interviews" className="rounded-2xl border border-blue-200 bg-blue-50 p-4 transition hover:border-blue-300"><p className="text-xs font-bold text-blue-700">Bài chờ đánh giá</p><p className="mt-2 text-2xl font-extrabold text-blue-950">{stats.data?.submitted_interviews || 0}</p><p className="mt-1 text-xs font-semibold text-blue-700/70">Đã nộp phỏng vấn</p></NavLink><NavLink to="/admin/ui/interviews" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 transition hover:border-emerald-300"><p className="text-xs font-bold text-emerald-700">Đã đánh giá</p><p className="mt-2 text-2xl font-extrabold text-emerald-950">{stats.data?.evaluated_interviews || 0}</p><p className="mt-1 text-xs font-semibold text-emerald-700/70">Có thể gửi kết quả</p></NavLink></div></Card>
    <div className="grid gap-6 xl:grid-cols-[1.45fr_.55fr]"><Card className="overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 p-5 sm:p-6"><div><p className="eyebrow">Luồng ứng viên</p><h2 className="section-title mt-2">Hồ sơ gần đây</h2></div><NavLink className="flex items-center gap-1 text-sm font-extrabold text-blue-600" to="/admin/ui/applications">Xem tất cả</NavLink></div><div className="divide-y divide-slate-100">{apps.isLoading?<Loading/>:apps.data?.applications?.length?apps.data.applications.map(item=><div key={item.id} className="group flex items-center gap-4 p-4 transition hover:bg-blue-50/50 sm:px-6"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 font-extrabold text-slate-600">{item.name?.charAt(0)}</span><div className="min-w-0 flex-1"><p className="truncate font-extrabold text-slate-900">{item.name}</p><p className="mt-1 truncate text-xs font-medium text-slate-500">{adminPositionName(item.job_id,item.application_source)} · {formatDate(item.applied_at)}</p></div><Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge></div>):<Empty title="Chưa có hồ sơ mới"/>}</div></Card><Card className="overflow-hidden p-6"><p className="eyebrow">Pipeline</p><h2 className="section-title mt-2">Phân bổ kết quả</h2><div className="mt-6 flex h-3 overflow-hidden rounded-full bg-slate-100">{pipeline.map(item=><span key={item.label} className={item.color} style={{width:(item.value/Math.max(total,1)*100)+'%'}}/>)}</div><div className="mt-7 space-y-5">{pipeline.map(item=>{const percent=Math.round(item.value/Math.max(total,1)*100);return <div key={item.label} className="flex items-center gap-3"><span className={cn('h-3 w-3 rounded-full',item.color)}/><div className="min-w-0 flex-1"><div className="flex justify-between text-sm"><span className="font-bold">{item.label}</span><span className="font-extrabold">{item.value}</span></div><p className="mt-1 text-xs font-semibold text-slate-400">{percent}% tổng hồ sơ</p></div></div>})}</div><NavLink to="/admin/ui/applications" className="btn-secondary mt-7 w-full">Mở trung tâm hồ sơ</NavLink></Card></div>
  </div>;
}
function Applications() {
  const [params] = useSearchParams(); const [query,setQuery] = useState(''); const [status,setStatus] = useState(params.get('status') || ''); const [selected,setSelected] = useState<string>();
  const result = useQuery({ queryKey:['applications',status], queryFn:()=>adminApi<{applications:Application[]}>(`/admin/applications?limit=200${status ? `&status=${encodeURIComponent(status)}`:''}`) });
  const rows = useMemo(() => (result.data?.applications || []).filter(a => `${a.name} ${a.email} ${adminPositionName(a.job_id,a.application_source)}`.toLowerCase().includes(query.toLowerCase())),[result.data,query]);
  return <><Card><div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row"><label className="relative flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400"/><input className="field pl-9" placeholder="Tìm tên, email hoặc vị trí..." value={query} onChange={e=>setQuery(e.target.value)} /></label><SelectField className="sm:w-64" value={status} onChange={setStatus} options={[{value:'',label:'Tất cả trạng thái'},{value:'pending',label:'Đang xử lý'},{value:'pending_hr_approval_passed',label:'Chờ HR duyệt · Đạt'},{value:'pending_hr_approval_failed',label:'Chờ HR duyệt · Chưa đạt'},{value:'passed',label:'Đã gửi phỏng vấn'},{value:'failed',label:'Không đạt'}]}/><Button variant="secondary" onClick={()=>result.refetch()}>Làm mới</Button></div>{result.isLoading ? <Loading/> : result.error ? <ErrorState message={result.error.message}/> : rows.length ? <ResponsiveApplications rows={rows} onSelect={setSelected}/> : <Empty title="Không tìm thấy hồ sơ" description="Thử thay đổi từ khóa hoặc bộ lọc." />}</Card><ApplicationDrawer appId={selected} onClose={()=>setSelected(undefined)} /></>;
}

function Pipeline(){
  const [job,setJob]=useState('');const [selected,setSelected]=useState<string>();
  const apps=useQuery({queryKey:['pipeline-applications'],queryFn:()=>adminApi<{applications:Application[]}>('/admin/applications?limit=300')});
  const jobs=useQuery({queryKey:['jobs-pipeline'],queryFn:()=>adminApi<{jobs:Job[]}>('/jobs?include_inactive=true')});
  const stages=[{key:'pending',label:'Hồ sơ mới',hint:'Cần xem xét',tone:'border-slate-200'},{key:'pending_hr_approval',label:'HR duyệt',hint:'Cần quyết định',tone:'border-amber-200'},{key:'passed',label:'Đã gửi phỏng vấn',hint:'Chờ ứng viên',tone:'border-blue-200'},{key:'completed',label:'Hoàn tất phỏng vấn',hint:'Đã nộp bài hoặc đã có kết quả',tone:'border-emerald-200'},{key:'failed',label:'Không đạt',hint:'Đã kết thúc',tone:'border-rose-200'}];
  const stageOf=(a:Application&{latest_interview_status?:string})=>{const interviewStatus=a.latest_interview_status;return a.status.startsWith('pending_hr_approval')?'pending_hr_approval':['submitted','pending_review','evaluated','reviewed','passed','failed'].includes(interviewStatus||'')||a.status==='interview_submitted'||a.status==='submitted'?'completed':a.status==='interview_link_sent'||a.status==='passed'?'passed':a.status==='failed'?'failed':'pending';};
  const data=(apps.data?.applications||[]).filter(a=>!job||a.job_id===job);
  return <div className="space-y-5"><Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow">Tuyển dụng theo giai đoạn</p><h2 className="section-title mt-2">Pipeline ứng viên</h2><p className="muted mt-1">Chọn hồ sơ để xem chi tiết và thực hiện bước tiếp theo.</p></div><div className="w-full sm:w-72"><SelectField value={job} onChange={setJob} options={[{value:'',label:'Tất cả vị trí'},...(jobs.data?.jobs||[]).map(item=>({value:item.id,label:positionName(item.title)}))]}/></div></div></Card>{apps.isLoading?<Loading/>:apps.error?<ErrorState message={apps.error.message}/>:<div className="flex gap-4 overflow-x-auto pb-4">{stages.map(stage=>{const items=data.filter(a=>stageOf(a)===stage.key);return <section key={stage.key} className={cn('min-w-[270px] flex-1 rounded-2xl border bg-slate-50/70 p-3',stage.tone)}><div className="flex items-start justify-between gap-3 px-2 pb-3"><div><h3 className="font-extrabold">{stage.label}</h3><p className="mt-1 text-xs text-slate-500">{stage.hint}</p></div><span className="grid h-7 min-w-7 place-items-center rounded-full bg-white text-xs font-extrabold text-slate-700 shadow-sm">{items.length}</span></div><div className="space-y-3">{items.map(app=><button key={app.id} onClick={()=>setSelected(app.id)} className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-blue-300 hover:shadow"><p className="font-extrabold text-slate-900">{app.name}</p><p className="mt-1 text-xs font-semibold text-slate-500">{adminPositionName(app.job_id,app.application_source)}</p><div className="mt-3 flex items-center justify-between text-xs"><span className="text-slate-400">{formatDate(app.applied_at,true)}</span><Badge tone={statusTone(app.status)}>{statusLabel(app.status)}</Badge></div></button>)}{!items.length&&<p className="rounded-xl border border-dashed border-slate-200 bg-white/60 p-4 text-center text-xs text-slate-400">Không có hồ sơ</p>}</div></section>})}</div>}<ApplicationDrawer appId={selected} onClose={()=>setSelected(undefined)}/></div>;
}

export function ResponsiveApplications({rows,onSelect}:{rows:Application[];onSelect:(id:string)=>void}) {
  return <><div className="hidden overflow-x-auto md:block"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Ứng viên</th><th className="px-5 py-3">Vị trí</th><th className="px-5 py-3">Điểm CV</th><th className="px-5 py-3">Trạng thái</th><th className="px-5 py-3">Ngày nộp</th><th className="px-5 py-3"/></tr></thead><tbody className="divide-y divide-slate-100">{rows.map(a=><tr key={a.id} onClick={()=>onSelect(a.id)} className="cursor-pointer hover:bg-blue-50"><td className="px-5 py-4"><p className="font-bold">{a.name}</p><p className="text-xs text-slate-500">{a.email}</p></td><td className="px-5 py-4">{adminPositionName(a.job_id,a.application_source)}</td><td className="px-5 py-4 font-extrabold">{cvScoreLabel(a.cv_score)}</td><td className="px-5 py-4"><Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge></td><td className="px-5 py-4 text-slate-500">{formatDate(a.applied_at)}</td><td className="px-5 py-4 text-right"><button className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-extrabold text-brand-700 hover:bg-white" onClick={event=>{event.stopPropagation();onSelect(a.id)}}>Xem hồ sơ</button></td></tr>)}</tbody></table></div><div className="divide-y divide-slate-100 md:hidden">{rows.map(a=><button key={a.id} onClick={()=>onSelect(a.id)} className="w-full p-4 text-left hover:bg-slate-50"><div className="flex items-start justify-between gap-3"><div><p className="font-bold">{a.name}</p><p className="mt-1 text-xs text-slate-500">{a.email}</p></div><Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge></div><div className="mt-3 flex items-center justify-between text-sm"><span>{adminPositionName(a.job_id,a.application_source)}</span><strong>{cvScoreLabel(a.cv_score)}</strong></div></button>)}</div></>;
}

function ApplicationDrawer({appId,onClose}:{appId?:string;onClose:()=>void}) {
  const qc=useQueryClient(); const detail=useQuery({queryKey:['application',appId],queryFn:()=>adminApi<Application>(`/admin/applications/${appId}`),enabled:!!appId});
  const [confirm,setConfirm]=useState<'approve'|'reject'>();
  const refresh=()=>{qc.invalidateQueries({queryKey:['applications']});qc.invalidateQueries({queryKey:['admin-stats']});qc.invalidateQueries({queryKey:['application',appId]});};
  const action=useMutation({mutationFn:(kind:'approve'|'reject')=>kind==='reject'?adminApi(`/admin/applications/${appId}/reject`,{method:'POST'}):adminApi(`/admin/applications/${appId}/approve`,{method:'POST'}),onSuccess:()=>{setConfirm(undefined);refresh();}});
  return <><Drawer open={!!appId} onClose={onClose} title={detail.data?.name || 'Chi tiết hồ sơ'} footer={detail.data && <div className="space-y-3"><div className="flex flex-wrap justify-end gap-2"><Button variant="danger" onClick={()=>setConfirm('reject')}>Từ chối hồ sơ</Button>{detail.data.status.startsWith('pending_hr_approval') && <Button onClick={()=>setConfirm('approve')}>Gửi link phỏng vấn</Button>}</div></div>}>{detail.isLoading?<Loading/>:detail.error?<ErrorState message={detail.error.message}/>:detail.data?<ApplicationDetails data={detail.data} refresh={refresh}/>:null}</Drawer><Dialog open={!!confirm} onClose={()=>setConfirm(undefined)} title={confirm==='approve'?'Gửi thư mời phỏng vấn?':'Từ chối hồ sơ?'} description={confirm==='approve'?'Hệ thống sẽ tạo link theo khung giờ đã cấu hình và gửi email cho ứng viên.':'Ứng viên sẽ nhận email thông báo kết quả không đạt.'} danger={confirm==='reject'} confirmLabel={action.isPending?'Đang xử lý...':confirm==='approve'?'Gửi thư mời':'Xác nhận từ chối'} onConfirm={()=>confirm&&action.mutate(confirm)}/></>;
}

function LegacyApplicationDetails({data,refresh}:{data:Application;refresh:()=>void}) {
  return <div className="space-y-4"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-slate-500">{data.email} · {data.phone || 'Chưa có số điện thoại'}</p><h3 className="mt-1 text-lg font-extrabold">{positionName(data.job_id)}</h3></div><Badge tone={statusTone(data.status)}>{statusLabel(data.status)}</Badge></div><div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3"><Info label="Điểm CV" value={data.cv_score==null?'Chưa chấm':`${data.cv_score}/5`}/><Info label="Cấp độ" value={levelName(data.level)}/><Info label="Ngày nộp" value={formatDate(data.applied_at)}/></div>{data.ai_summary&&<p className="mt-4 rounded-xl bg-blue-50 p-4 text-sm leading-6 text-blue-950">{data.ai_summary}</p>}</Card><QuestionEditor app={data} refresh={refresh}/><Card className="p-5"><h3 className="font-extrabold">Tiến trình hồ sơ</h3><div className="mt-4 space-y-4">{data.application_logs?.length?data.application_logs.map((log,index)=><div className="relative flex gap-3" key={log.id||index}><span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand-600"/><div><p className="text-sm font-semibold">{log.message}</p><p className="mt-1 text-xs text-slate-500">{formatDate(log.created_at)}</p></div></div>):<p className="muted">Chưa có hoạt động.</p>}</div></Card><Evaluation appId={data.id}/></div>;
}

function ApplicationDetails({data,refresh}:{data:Application;refresh:()=>void}) {
  const logs=(data.application_logs||[]).filter(log=>!['cv_scored','application_scored_api'].includes(log.event_type));
  return <div className="space-y-4"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-slate-500">{data.email} · {data.phone||'Chưa có số điện thoại'}</p><h3 className="mt-1 text-lg font-extrabold">{adminPositionName(data.job_id,data.application_source)}</h3></div><Badge tone={statusTone(data.status)}>{statusLabel(data.status)}</Badge></div><div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3"><Info label="Điểm CV" value={cvScoreLabel(data.cv_score)}/><Info label="Cấp độ" value={levelName(data.level)}/><Info label="Ngày nộp" value={formatDate(data.applied_at)}/></div></Card><CvScoreBreakdown data={data}/><ReplyScoreAdjustment data={data}/><QuestionEditor app={data} refresh={refresh}/><Card className="p-5"><h3 className="font-extrabold">Tiến trình hồ sơ</h3><p className="mt-1 text-xs text-slate-500">Chỉ hiển thị các mốc xử lý hồ sơ và phỏng vấn.</p><div className="mt-4 space-y-4">{logs.length?logs.map((log,index)=><div className="relative flex gap-3" key={log.id||index}><span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand-600"/><div><p className="text-sm font-semibold">{log.message}</p><p className="mt-1 text-xs text-slate-500">{formatDate(log.created_at)}</p></div></div>):<p className="muted">Chưa có hoạt động xử lý khác.</p>}</div></Card></div>;
}

function CvScoreBreakdown({data}:{data:Application}) {
  const breakdown=(data.score_breakdown||{}) as Record<string, unknown>;
  const map=(value:unknown)=>(value&&typeof value==='object'?value as Record<string,unknown>:{});
  const oldGroup1=map(breakdown.group1),oldGroup2=map(breakdown.group2),work=map(oldGroup1.work_experience),education=map(oldGroup1.education);
  const oldRows=[['Số năm kinh nghiệm',work.years,2],['Tính liên quan ngành',work.relevance,1],['Thành tích cá nhân',work.achievements,0.5],['Bằng cấp',education.degree,1],['Chuyên ngành',education.major,1],['Chứng chỉ',education.certs,0.5],['Kỹ năng chuyên môn',oldGroup1.technical_skills,1],['Chất lượng CV',oldGroup2.cv_quality,1],['Dự án & Portfolio',oldGroup2.projects,1],['Lãnh đạo & Teamwork',oldGroup2.leadership,1]].map(([label,value,max])=>({label:String(label),value:Number(value),max:Number(max)})).filter(row=>Number.isFinite(row.value));
  if(oldRows.length){const oldTotal=oldRows.reduce((sum,row)=>sum+Math.max(0,Math.min(row.value,row.max)),0);return <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="font-extrabold">Chấm chi tiết CV</h3><p className="mt-1 text-xs text-slate-500">Phiếu chấm CV gốc · thang điểm 10.</p></div><Badge tone="info">Tổng điểm: {oldTotal.toFixed(1)}/10</Badge></div><div className="mt-5 space-y-3">{oldRows.map(row=><div key={row.label}><div className="flex items-center justify-between gap-3 text-sm"><span className="font-semibold text-slate-700">{row.label}</span><strong className="text-brand-700">{row.value.toFixed(1)}/{row.max}</strong></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"><span className="block h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" style={{width:`${Math.max(0,Math.min(row.value,row.max))/row.max*100}%`}}/></div></div>)}</div>{data.ai_summary&&<p className="mt-5 rounded-xl bg-blue-50 p-4 text-sm leading-6 text-blue-950">{data.ai_summary}</p>}</Card>;}
  const scores=(breakdown.criteria_scores||{}) as Record<string, unknown>;
  const labels:Record<string,string>={c1_technical_skills:'Kỹ năng chuyên môn',c2_experience:'Kinh nghiệm làm việc',c3_education:'Học vấn',c4_industry:'Mức độ phù hợp ngành',c5_career_path:'Lộ trình nghề nghiệp',c6_achievements:'Thành tích',c7_soft_skills:'Kỹ năng mềm',c8_language_cv:'Ngôn ngữ & trình bày CV',c9_stability:'Tính ổn định',c10_ai_overall:'Đánh giá tổng quan'};
  const weights=(breakdown.criteria_weights||{}) as Record<string, unknown>;
  const reasons=(breakdown.reasons||{}) as Record<string, unknown>;
  const rows=Object.entries(scores).map(([key,value])=>({key,label:labels[key]||key.replaceAll('_',' '),score:Number(value),weight:Number(weights[key]||0),reason:typeof reasons[key]==='string'?reasons[key]:''})).filter(item=>Number.isFinite(item.score));
  if(!rows.length)return null;
  return <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="font-extrabold">Chấm chi tiết CV</h3><p className="mt-1 text-xs text-slate-500">Mỗi tiêu chí chấm thang 1–5, sau đó quy đổi theo trọng số vào tổng điểm 5.</p></div><Badge tone="info">Tổng điểm: {cvScoreLabel(data.cv_score)}</Badge></div><div className="mt-5 space-y-4">{rows.map(item=>{const max=item.weight>0?5*item.weight:0;const converted=item.weight>0?item.score*item.weight:0;return <div key={item.key} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-extrabold text-slate-800">{item.label}</p><p className="mt-1 text-xs text-slate-500">Mốc chấm: 1–5 · Trọng số: {Math.round(item.weight*100)}%{item.weight>0&&` · Tối đa ${max.toFixed(2)} điểm quy đổi`}</p></div><div className="text-right"><p className="text-lg font-extrabold text-brand-700">{item.score.toFixed(1)}/5</p>{item.weight>0&&<p className="text-xs font-semibold text-slate-500">Quy đổi: {converted.toFixed(2)}/{max.toFixed(2)}</p>}</div></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200"><span className="block h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" style={{width:`${Math.max(0,Math.min(item.score,5))/5*100}%`}}/></div><div className="mt-3 rounded-xl border border-blue-100 bg-white p-3"><p className="text-xs font-bold text-blue-700">Lý do chấm</p><p className="mt-1 text-sm leading-6 text-slate-700">{item.reason||'Chưa có lý do chi tiết được lưu cho tiêu chí này.'}</p></div></div>})}</div>{typeof breakdown.summary==='string'&&breakdown.summary&&<p className="mt-5 rounded-xl bg-blue-50 p-4 text-sm leading-6 text-blue-950">{breakdown.summary}</p>}</Card>;
}

function ReplyScoreAdjustment({data}:{data:Application}) {
  const breakdown=(data.score_breakdown||{}) as Record<string,unknown>;
  const analysis=breakdown.reply_analysis&&typeof breakdown.reply_analysis==='object'?breakdown.reply_analysis as Record<string,unknown>:{};
  const reply=typeof breakdown.candidate_reply==='string'?breakdown.candidate_reply.trim():'';
  const deepQuestions=Array.isArray(breakdown.deep_questions)?breakdown.deep_questions:[];
  const before=Number(analysis.score_before), adjustment=Number(analysis.score_adjustment), after=Number(analysis.score_after);
  const adjustmentLabel=Number.isFinite(adjustment)?`${adjustment>0?'+':''}${adjustment.toFixed(1)} điểm`:'Chưa cập nhật';
  const reason=typeof analysis.score_adjustment_reason==='string'?analysis.score_adjustment_reason:typeof analysis.evaluation==='string'?analysis.evaluation:'';
  if(!deepQuestions.length&&!reply&&!Number.isFinite(adjustment))return null;
  return <div className="space-y-4">{deepQuestions.length>0&&<Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-extrabold">Câu hỏi bổ sung đã gửi</h3><p className="mt-1 text-xs text-slate-500">Hiển thị ngay sau khi gửi email. Ứng viên chưa trả lời thì chưa có phần đánh giá.</p></div><Badge tone={reply?'success':'warning'}>{reply?'Đã nhận phản hồi':'Đang chờ phản hồi'}</Badge></div><div className="mt-4 space-y-3">{deepQuestions.map((question,index)=>{const item=question&&typeof question==='object'?question as Record<string,unknown>:{};const text=typeof question==='string'?question:typeof item.question_text==='string'?item.question_text:typeof item.text==='string'?item.text:'';const category=typeof item.category==='string'?item.category:typeof item.type==='string'?item.type:'';return <div key={`${index}-${text}`} className="rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><span className="text-xs font-extrabold text-brand-700">CÂU BỔ SUNG {index+1}</span>{category&&<Badge tone="info">{category}</Badge>}</div><p className="mt-2 text-sm leading-6 text-slate-800">{text||'Nội dung câu hỏi chưa hợp lệ.'}</p></div>})}</div></Card>}{(reply||Number.isFinite(adjustment))&&<Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-extrabold">Đánh giá câu trả lời bổ sung</h3><p className="mt-1 text-xs text-slate-500">Điểm được điều chỉnh sau khi HR nhận và phân tích câu trả lời bổ sung.</p></div><Badge tone={adjustment>0?'success':adjustment<0?'danger':'neutral'}>{adjustmentLabel}</Badge></div><div className="mt-5 grid gap-3 sm:grid-cols-3"><Info label="Điểm trước điều chỉnh" value={Number.isFinite(before)?before.toFixed(1)+'/5':'—'}/><Info label="Cộng / trừ" value={adjustmentLabel}/><Info label="Điểm sau điều chỉnh" value={Number.isFinite(after)?after.toFixed(1)+'/5':cvScoreLabel(data.cv_score)}/></div>{reason&&<div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 p-4"><p className="text-xs font-extrabold text-blue-800">Lý do cộng / trừ điểm</p><p className="mt-1 text-sm leading-6 text-blue-950">{reason}</p></div>}{reply&&<details className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4"><summary className="cursor-pointer text-sm font-extrabold text-slate-800">Xem câu trả lời của ứng viên</summary><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{reply}</p></details>}</Card>}</div>;
}

export function QuestionEditor({app,refresh}:{app:Application;refresh:()=>void}) {
  const initialDate=(offsetHours:number)=>{const date=new Date(Date.now()+offsetHours*60*60*1000);date.setMinutes(date.getMinutes()-date.getTimezoneOffset());return date.toISOString().slice(0,16)};
  const original=app.interview_prep?.questions||[];
  const [questions,setQuestions]=useState<PrepQuestion[]>(original);
  const [editing,setEditing]=useState(false);
  const [setupOpen,setSetupOpen]=useState(false);
  const [validFrom,setValidFrom]=useState(()=>initialDate(1));
  const [validUntil,setValidUntil]=useState(()=>initialDate(2));
  const [part1,setPart1]=useState('11'); const [part2,setPart2]=useState('7'); const [part3,setPart3]=useState('5');
  const changed=questions.filter(q=>(q.text||'').trim()!==(original.find(o=>o.n===q.n)?.text||'').trim());
  const validSchedule=Boolean(validFrom&&validUntil&&validUntil>validFrom);
  const generate=useMutation({
    mutationFn:(config:Record<string,unknown>)=>adminApi<{ok:boolean}>(`/admin/applications/${app.id}/generate_prep`,jsonInit('POST',{config})),
    onSuccess:()=>{setSetupOpen(false);refresh();},
  });
  const save=useMutation({mutationFn:()=>adminApi(`/admin/applications/${app.id}/prep`,jsonInit('PATCH',{questions:Object.fromEntries(changed.map(q=>[q.n,q.text]))})),onSuccess:()=>{setEditing(false);refresh();}});
  
  useEffect(() => {
    if (app.prep_status === 'generating') {
      const interval = setInterval(() => { refresh(); }, 3000);
      return () => clearInterval(interval);
    }
  }, [app.prep_status, refresh]);
  
  useEffect(() => {
    setQuestions(app.interview_prep?.questions || []);
  }, [app.interview_prep?.questions]);
  
  const shown=questions.length?questions:original;
  
  return <><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-extrabold">Câu hỏi phỏng vấn</h3><p className="mt-1 text-xs text-slate-500">Chỉ câu được sửa mới tạo lại audio.</p></div><div className="flex gap-2">
  {app.prep_status === 'generating' ? (
    <span className="animate-pulse"><Badge tone="info">Đang xử lý...</Badge></span>
  ) : (
    <>
      {shown.length>0&&<Button variant="secondary" onClick={()=>setEditing(!editing)}>{editing?'Hủy sửa':'Sửa câu hỏi'}</Button>}
      <Button onClick={()=>setSetupOpen(true)} disabled={generate.isPending}>{generate.isPending?'Đang xử lý...':(shown.length?'Tạo lại':'Tạo bộ câu hỏi')}</Button>
    </>
  )}
  </div></div>{shown.length>0&&app.prep_status!=='generating'&&<div className="mt-5 space-y-3">{shown.map(q=><div key={q.n} className={cn('rounded-xl border p-4',changed.some(c=>c.n===q.n)?'border-amber-300 bg-amber-50':'border-slate-200 bg-slate-50')}><div className="mb-2 flex items-center justify-between"><span className="text-xs font-extrabold text-brand-700">{q.label||`Câu ${q.n}`}</span>{changed.some(c=>c.n===q.n)&&<Badge tone="warning">Đã thay đổi</Badge>}</div>{editing?<RichTextEditor value={q.text||''} onChange={text=>setQuestions(old=>old.map(item=>item.n===q.n?{...item,text}:item))} placeholder="Nhập nội dung câu hỏi..." minHeight="min-h-24"/>:<p className="whitespace-pre-wrap text-sm leading-6">{q.text}</p>}</div>)}</div>}{editing&&app.prep_status!=='generating'&&<div className="mt-4 flex items-center justify-between gap-3"><p className="text-xs text-slate-500">{changed.length} câu đã thay đổi</p><Button disabled={!changed.length||save.isPending||changed.some(q=>!(q.text||'').trim())} onClick={()=>save.mutate()}>{save.isPending?'Đang lưu...':'Lưu thay đổi'}</Button></div>}{(generate.error||save.error)&&<p className="mt-3 text-sm text-red-700">{(generate.error||save.error)?.message}</p>}</Card><Dialog open={setupOpen} onClose={()=>setSetupOpen(false)} title="Tạo bộ câu hỏi phỏng vấn" description="Chọn khung giờ ứng viên được phép mở link, rồi cấu hình số lượng câu hỏi trước khi tạo." confirmLabel={generate.isPending?'Đang xử lý...':'Tạo bộ câu hỏi'} onConfirm={()=>generate.mutate({PART_1_DEFAULT:Number(part1),PART_2_GENERATED:Number(part2),PART_3_FOLLOW_UP:Number(part3),IS_UNLIMITED:false,VALID_FROM:validFrom,VALID_UNTIL:validUntil})}><div className="mt-5 space-y-4"><div className="grid gap-3 sm:grid-cols-2"><label><span className="label">Bắt đầu truy cập link</span><input className="field" type="datetime-local" value={validFrom} onChange={e=>setValidFrom(e.target.value)} required/></label><label><span className="label">Kết thúc truy cập link</span><input className="field" type="datetime-local" value={validUntil} onChange={e=>setValidUntil(e.target.value)} required/></label></div>{!validSchedule&&<p className="rounded-xl bg-red-50 p-3 text-xs font-semibold text-red-700">Giờ kết thúc phải sau giờ bắt đầu.</p>}<div className="grid gap-3 sm:grid-cols-3"><label><span className="label">Câu nền tảng</span><input className="field" type="number" min="1" max="11" value={part1} onChange={e=>setPart1(e.target.value)}/></label><label><span className="label">Câu theo CV/JD</span><input className="field" type="number" min="0" max="13" value={part2} onChange={e=>setPart2(e.target.value)}/></label><label><span className="label">Câu đào sâu tối đa</span><input className="field" type="number" min="0" max="5" value={part3} onChange={e=>setPart3(e.target.value)}/></label></div><p className="text-xs leading-5 text-slate-500">Câu đào sâu chỉ được AI hỏi thêm khi câu trả lời cần làm rõ. Khung giờ này sẽ tự dùng khi gửi email mời phỏng vấn.</p></div></Dialog></>;
}

type EvaluationRecord={round:number;evaluator?:string;decision?:string;data?:{summary?:string};updated_at?:string};
function Evaluation({appId}:{appId:string}) { const [round,setRound]=useState(1); const [summary,setSummary]=useState(''); const [decision,setDecision]=useState('pending'); const query=useQuery({queryKey:['evaluations',appId],queryFn:()=>adminApi<{evaluations:EvaluationRecord[]}>(`/admin/applications/${appId}/evaluation`)}); const current=query.data?.evaluations.find(item=>item.round===round); useEffect(()=>{setSummary(current?.data?.summary||'');setDecision(current?.decision||'pending')},[round,current?.decision,current?.data?.summary]); const save=useMutation({mutationFn:()=>adminApi(`/admin/applications/${appId}/evaluation`,jsonInit('POST',{round,evaluator:localStorage.getItem('pai_admin_name')||'HR',decision,data:{summary,criteria:[]}})),onSuccess:()=>query.refetch()}); const rounds=[{id:1,label:'Vòng 1 · HR'},{id:2,label:'Vòng 2 · Chuyên môn'},{id:3,label:'Vòng 3 · Quyết định'}]; return <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="font-extrabold">Phiếu đánh giá phỏng vấn · 3 vòng</h3><p className="mt-1 text-xs text-slate-500">Lưu riêng nhận xét và quyết định cho từng vòng.</p></div>{query.isLoading?<span className="text-xs text-slate-400">Đang tải...</span>:null}</div><div className="mt-5 grid gap-3 sm:grid-cols-3">{rounds.map(item=>{const saved=query.data?.evaluations.find(value=>value.round===item.id);return <button type="button" key={item.id} onClick={()=>setRound(item.id)} className={cn('rounded-2xl border p-4 text-left transition',round===item.id?'border-blue-400 bg-blue-50 ring-2 ring-blue-100':'border-slate-200 bg-white hover:bg-slate-50')}><p className="text-sm font-extrabold">{item.label}</p><p className="mt-2 text-xs text-slate-500">{saved?`Đã lưu · ${saved.decision==='pass'?'Đạt':saved.decision==='fail'?'Không đạt':'Chờ quyết định'}`:'Chưa đánh giá'}</p></button>})}</div><div className="mt-5 rounded-2xl bg-slate-50 p-4"><div className="grid gap-3 sm:grid-cols-2"><div><span className="label">Kết quả vòng {round}</span><SelectField value={decision} onChange={setDecision} options={[{value:'pending',label:'Chờ quyết định'},{value:'pass',label:'Đạt'},{value:'fail',label:'Không đạt'}]}/></div><div><span className="label">Người đánh giá</span><input className="field" value={current?.evaluator||localStorage.getItem('pai_admin_name')||'HR'} disabled/></div></div><label className="mt-3 block"><span className="label">Nhận xét vòng {round}</span><RichTextEditor value={summary} onChange={setSummary} minHeight="min-h-24" placeholder="Nhập nhận xét của người đánh giá..."/></label><div className="mt-3 flex items-center justify-between gap-3"><p className="text-xs text-slate-400">{current?.updated_at?`Cập nhật ${formatDate(current.updated_at)}`:'Chưa lưu phiếu này'}</p><Button onClick={()=>save.mutate()} disabled={save.isPending}>{save.isPending?'Đang lưu...':'Lưu phiếu vòng này'}</Button></div>{save.isSuccess&&<p className="mt-3 text-sm font-semibold text-emerald-700">Đã lưu phiếu đánh giá.</p>}</div></Card>; }

function Interviews() { const [selected,setSelected]=useState<string>(); const query=useQuery({queryKey:['interviews'],queryFn:()=>adminApi<{interviews:Interview[]}>('/admin/interviews?limit=200')}); return <><Card>{query.isLoading?<Loading/>:query.error?<ErrorState message={query.error.message}/>:query.data?.interviews?.length?<div className="divide-y divide-slate-100">{query.data.interviews.map(iv=><button key={iv.id} onClick={()=>setSelected(iv.id)} className="flex w-full items-center gap-4 p-4 text-left hover:bg-slate-50"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-blue-50 font-bold text-brand-700">{iv.candidate_name?.charAt(0)||'Ư'}</span><div className="min-w-0 flex-1"><p className="truncate font-bold">{iv.candidate_name||'Ứng viên chưa rõ tên'}</p><p className="truncate text-xs text-slate-500">{positionName(iv.position_id)} · {formatDate(iv.submitted_at)}</p></div><div className="hidden text-right sm:block"><p className="font-extrabold">{iv.avg_score==null?'—':`${iv.avg_score}/10`}</p><p className="text-xs text-slate-500">{iv.answer_count||0} câu trả lời</p></div><Badge tone={statusTone(iv.status)}>{statusLabel(iv.status)}</Badge></button>)}</div>:<Empty title="Chưa có bài phỏng vấn"/>}</Card><InterviewDrawerPro id={selected} onClose={()=>setSelected(undefined)}/></>; }

function InterviewDrawer({id,onClose}:{id?:string;onClose:()=>void}) { const qc=useQueryClient(); const detail=useQuery({queryKey:['interview',id],queryFn:()=>adminApi<Interview>(`/interview/${id}`),enabled:!!id}); const review=useMutation({mutationFn:(status:string)=>adminApi(`/interview/${id}/review`,jsonInit('PATCH',{status})),onSuccess:()=>{qc.invalidateQueries({queryKey:['interviews']});detail.refetch();}}); return <Drawer open={!!id} onClose={onClose} title={detail.data?.candidate_name||'Chi tiết phỏng vấn'} footer={detail.data&&<div className="flex justify-end gap-2"><Button variant="danger" onClick={()=>review.mutate('failed')}>Không đạt</Button><Button onClick={()=>review.mutate('passed')}>Đạt phỏng vấn</Button></div>}>{detail.isLoading?<Loading/>:detail.error?<ErrorState message={detail.error.message}/>:detail.data?<div className="space-y-4"><Card className="p-5"><div className="flex justify-between"><div><p className="muted">{positionName(detail.data.position_id)}</p><p className="mt-1 text-2xl font-extrabold">{detail.data.avg_score==null?'Chưa có điểm':`${detail.data.avg_score}/10`}</p></div><Badge tone={statusTone(detail.data.status)}>{statusLabel(detail.data.status)}</Badge></div></Card>{detail.data.answers?.map((a,index)=><Card className="p-5" key={`${a.question_number}-${index}`}><p className="text-xs font-extrabold text-brand-700">CÂU {a.question_number}</p><h3 className="mt-2 font-bold leading-6">{a.question_text||'Nội dung câu hỏi'}</h3><div className="mt-3 rounded-xl bg-slate-50 p-4 text-sm leading-6">{a.transcript||'Không có bản ghi nội dung.'}</div>{a.ai_feedback&&<p className="mt-3 text-sm text-slate-600"><strong>Nhận xét AI:</strong> {a.ai_feedback}</p>}</Card>)||<Empty/>}</div>:null}</Drawer>; }

function Feedback() { const result=useQuery({queryKey:['feedback'],queryFn:()=>adminApi<{total_responses:number;by_position:FeedbackStat[]}>('/admin/feedback/stats')}); if(result.isLoading)return <Loading/>; if(result.error)return <ErrorState message={result.error.message}/>; return <div className="space-y-4"><Card className="p-6"><p className="muted">Tổng lượt phản hồi</p><p className="mt-2 text-4xl font-extrabold">{result.data?.total_responses||0}</p></Card><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{result.data?.by_position.map(item=><Card className="p-5" key={item.position_id}><h3 className="font-extrabold">{positionName(item.position_id)}</h3><div className="mt-4 flex gap-6"><Info label="Lượt trả lời" value={item.count}/><Info label="NPS trung bình" value={item.avg_nps??'—'}/></div></Card>)}</div></div>; }

function Jobs() {
  const queryClient=useQueryClient();
  const jobs=useQuery({queryKey:['jobs-admin'],queryFn:()=>adminApi<{jobs:Job[];categories:string[]}>('/jobs?include_inactive=true')});
  const [selectedId,setSelectedId]=useState('');
  const [editing,setEditing]=useState(false);
  const [loadingDetail,setLoadingDetail]=useState(false);
  const [search,setSearch]=useState('');
  const [categoryFilter,setCategoryFilter]=useState('');
  const [title,setTitle]=useState('');
  const [category,setCategory]=useState('Khối chuyên môn');
  const [jd,setJd]=useState<JdSections>(emptyJd);
  const content=composeJd(jd);
  const [salary,setSalary]=useState('AUTO');
  const [locationValue,setLocationValue]=useState('TP. Hồ Chí Minh (CT Group Tower)');
  const [workTypeValue,setWorkTypeValue]=useState('Toàn thời gian');
  const [isActive,setIsActive]=useState(true);
  const list=useMemo(()=>uniquePositions(jobs.data?.jobs||[]).filter(job=>
    (!categoryFilter||job.category===categoryFilter)&&
    (!search||(positionName(job.title)+' '+(job.category||'')).toLowerCase().includes(search.toLowerCase()))
  ),[jobs.data,categoryFilter,search]);
  const resetForm=()=>{
    setSelectedId('');setTitle('');setCategory('Khối chuyên môn');setJd(emptyJd());
    setSalary('AUTO');setLocationValue('TP. Hồ Chí Minh (CT Group Tower)');
    setWorkTypeValue('Toàn thời gian');setIsActive(true);setEditing(true);
  };
  const openJob=async(job:Job)=>{
    setSelectedId(job.id);setEditing(true);setLoadingDetail(true);
    try{
      const detail=await adminApi<Job>('/jobs/'+encodeURIComponent(job.id)+'?level=Junior&include_inactive=true');
      setTitle(positionName(detail.title||job.title));
      setCategory(detail.category||job.category||'Khối chuyên môn');
      setJd(parseJd(detail.jd_content||''));
      setSalary(detail.salary_range||'AUTO');
      setLocationValue(detail.location||'TP. Hồ Chí Minh (CT Group Tower)');
      setWorkTypeValue(detail.work_type||'Toàn thời gian');
      setIsActive(detail.is_active!==false);
    }finally{setLoadingDetail(false)}
  };
  const save=useMutation({
    mutationFn:()=>adminApi<{id:string;salary_range:string}>('/jobs/save-jd',jsonInit('POST',{
      id:selectedId||undefined,title,category,jd_content:content,
      salary_range:salary,location:locationValue,work_type:workTypeValue,
      is_active:isActive,
    })),
    onSuccess:async data=>{
      const savedJob:Job={id:data.id,title,category,jd_content:content,salary_range:data.salary_range,location:locationValue,work_type:workTypeValue,is_active:isActive};
      queryClient.setQueryData<{jobs:Job[];categories:string[]}>(['jobs-admin'],old=>{
        if(!old)return {jobs:[savedJob],categories:[category]};
        const exists=old.jobs.some(item=>item.id===data.id);
        const nextJobs=exists?old.jobs.map(item=>item.id===data.id?{...item,...savedJob}:item):[savedJob,...old.jobs];
        return {jobs:nextJobs,categories:[...new Set([...old.categories,category])].sort()};
      });
      setSelectedId(data.id);
      await Promise.all([jobs.refetch(),queryClient.invalidateQueries({queryKey:['jobs']})]);
    },
  });
  const toggleActive=useMutation({
    mutationFn:({id,is_active}:{id:string;is_active:boolean})=>adminApi<{id:string;is_active:boolean}>(`/jobs/${encodeURIComponent(id)}/active`,jsonInit('PATCH',{is_active})),
    onSuccess:data=>queryClient.setQueryData<{jobs:Job[];categories:string[]}>(['jobs-admin'],old=>old?{...old,jobs:old.jobs.map(job=>job.id===data.id?{...job,is_active:data.is_active}:job)}:old),
  });
  return <div className="grid gap-5 xl:grid-cols-[.72fr_1.28fr]">
    <Card className="overflow-visible">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-center justify-between gap-3"><div><h2 className="font-extrabold">Danh sách vị trí</h2><p className="mt-1 text-xs text-slate-500">{list.length} vị trí · {list.filter(job=>job.is_active!==false).length} đang hiển thị trên Apply</p></div><Button onClick={resetForm}>Tạo vị trí mới</Button></div>
        <label className="relative mt-4 block"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400"/><input className="field pl-9" placeholder="Tìm tên vị trí..." value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <SelectField className="mt-2" value={categoryFilter} onChange={setCategoryFilter} options={[{value:'',label:'Tất cả lĩnh vực'},...(jobs.data?.categories||[]).map(item=>({value:item,label:item}))]}/>
      </div>
      {jobs.isLoading?<Loading/>:!list.length?<Empty title="Chưa có vị trí phù hợp"/>:<div className="max-h-[68vh] divide-y divide-slate-100 overflow-y-auto">{list.map(job=><div className={cn('w-full p-4 text-left transition hover:bg-slate-50',selectedId===job.id&&'bg-blue-50')} key={job.id}><div className="flex items-start justify-between gap-3"><button type="button" className="min-w-0 flex-1 text-left" onClick={()=>openJob(job)}><p className="font-extrabold text-slate-900">{positionName(job.title)}</p><p className="mt-1 text-xs text-slate-500">{job.category||'Khối chuyên môn'}</p></button><button type="button" aria-label={`${job.is_active!==false?'Tắt':'Bật'} vị trí ${positionName(job.title)}`} className={cn('shrink-0 rounded-xl px-3 py-2 text-xs font-extrabold transition',job.is_active!==false?'bg-emerald-50 text-emerald-700 hover:bg-emerald-100':'bg-slate-100 text-slate-600 hover:bg-slate-200')} onClick={()=>toggleActive.mutate({id:job.id,is_active:job.is_active===false})} disabled={toggleActive.isPending}>{job.is_active!==false?'Đang bật':'Đang tắt'}</button></div></div>)}</div>}
    </Card>
    <Card className="p-5 sm:p-6">
      {!editing?<Empty title="Chọn một vị trí để chỉnh sửa" description="Hoặc bấm “Tạo vị trí mới” để thêm công việc và JD mới."/>:loadingDetail?<Loading label="Đang tải nội dung JD..."/>:<>
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-extrabold uppercase tracking-wide text-brand-700">{selectedId?'Chỉnh sửa vị trí':'Vị trí mới'}</p><h2 className="mt-1 text-xl font-extrabold">{selectedId?title:'Tạo việc làm mới'}</h2><p className="mt-1 text-sm text-slate-500">Cập nhật thông tin hiển thị và nội dung tuyển dụng.</p></div></div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="sm:col-span-2"><span className="label">Tên vị trí bằng tiếng Việt</span><input className="field" value={title} onChange={e=>setTitle(e.target.value)} placeholder="Ví dụ: Chuyên viên phân tích dữ liệu"/></label>
          <div><span className="label">Lĩnh vực</span><SelectField value={category} onChange={setCategory} options={[...new Set([category,...(jobs.data?.categories||[]),'Khối chuyên môn'])].filter(Boolean).map(item=>({value:item,label:item}))}/></div>
          <label><span className="label">Hình thức làm việc</span><input className="field" value={workTypeValue} onChange={e=>setWorkTypeValue(e.target.value)}/></label>
          <label><span className="label">Địa điểm</span><input className="field" value={locationValue} onChange={e=>setLocationValue(e.target.value)}/></label>
          <div><span className="label">Mức lương gross</span><SelectField value={salary} onChange={setSalary} options={salaryOptions.some(item=>item.value===salary)?salaryOptions:[{value:salary,label:salary},...salaryOptions]}/><p className="mt-1.5 text-[11px] text-slate-500">Có thể chọn tự động để hệ thống áp khung thị trường theo chức danh và cấp bậc.</p></div>
          <div><span className="label">Hiển thị trên Apply</span><SelectField value={isActive?'active':'inactive'} onChange={value=>setIsActive(value==='active')} options={[{value:'active',label:'Đang kích hoạt · Hiện trên Apply'},{value:'inactive',label:'Tạm tắt · Ẩn khỏi Apply'}]}/><p className="mt-1.5 text-[11px] text-slate-500">Chỉ vị trí đang kích hoạt mới cho ứng viên nhìn thấy và nộp hồ sơ.</p></div>
          <StructuredJdEditor value={jd} onChange={setJd}/>
        </div>
        {(save.error)&&<p className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{save.error.message}</p>}
        {save.isSuccess&&<p className="mt-4 rounded-xl bg-emerald-50 p-3 text-sm font-bold text-emerald-700">Đã lưu vị trí tuyển dụng.</p>}
        <div className="mt-5 flex justify-end"><Button onClick={()=>save.mutate()} disabled={!title.trim()||!category.trim()||!jd.responsibilities.trim()||!jd.requirements.trim()||save.isPending}>{save.isPending?'Đang lưu...':selectedId?'Lưu thay đổi':'Tạo vị trí'}</Button></div>
      </>}
    </Card>
  </div>;
}

function StructuredJdEditor({value,onChange}:{value:JdSections;onChange:(value:JdSections)=>void}){
  const update=(field:keyof JdSections,text:string)=>onChange({...value,[field]:text});
  return <div className="space-y-4 sm:col-span-2"><div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4"><p className="font-extrabold text-blue-950">Nội dung mô tả công việc</p><p className="mt-1 text-xs leading-5 text-blue-700">Dùng thanh công cụ để in đậm, lập danh sách hoặc trích dẫn. Khi lưu, hệ thống tự chuyển về định dạng JD tương thích; không cần gõ Markdown.</p></div><label className="block"><span className="label">Tổng quan vị trí</span><RichTextEditor value={value.overview} onChange={text=>update('overview',text)} minHeight="min-h-24" placeholder="Ví dụ: Vai trò thuộc Khối Công nghệ, phối hợp cùng đội sản phẩm để..."/></label><label className="block"><span className="label">Trách nhiệm công việc *</span><RichTextEditor value={value.responsibilities} onChange={text=>update('responsibilities',text)} minHeight="min-h-36" placeholder={'Mỗi trách nhiệm một dòng\nPhát triển và vận hành sản phẩm\nPhối hợp với các phòng ban liên quan'}/></label><label className="block"><span className="label">Yêu cầu ứng viên *</span><RichTextEditor value={value.requirements} onChange={text=>update('requirements',text)} minHeight="min-h-36" placeholder={'Mỗi yêu cầu một dòng\nTối thiểu 2 năm kinh nghiệm\nKỹ năng giao tiếp và làm việc nhóm tốt'}/></label><label className="block"><span className="label">Quyền lợi</span><RichTextEditor value={value.benefits} onChange={text=>update('benefits',text)} minHeight="min-h-28" placeholder={'Mỗi quyền lợi một dòng\nThưởng theo hiệu quả công việc\nBảo hiểm và ngày phép đầy đủ'}/></label><label className="block"><span className="label">Thông tin khác</span><RichTextEditor value={value.other} onChange={text=>update('other',text)} minHeight="min-h-24" placeholder="Thời gian làm việc, quy trình phỏng vấn hoặc ghi chú bổ sung..."/></label></div>;
}

function SystemSettings() { const settings=useQuery({queryKey:['settings'],queryFn:()=>adminApi<Record<string,string>>('/admin/settings')}); const [score,setScore]=useState('3.5'); const save=useMutation({mutationFn:()=>adminApi('/admin/settings',jsonInit('POST',{cv_pass_score:Number(score)}))}); if(settings.isLoading)return <Loading/>; return <Card className="max-w-2xl p-6"><h2 className="section-title">Ngưỡng duyệt CV</h2><p className="muted mt-2">Hồ sơ đạt ngưỡng sẽ chuyển sang bước HR xem xét trước khi gửi link.</p><label className="mt-6 block"><span className="label">Điểm tối thiểu trên thang 5</span><input className="field" type="number" min="0" max="5" step="0.1" value={score} onChange={e=>setScore(e.target.value)} /></label><div className="mt-4 flex justify-end"><Button onClick={()=>save.mutate()}>Lưu thiết lập</Button></div></Card>; }

function Info({label,value}:{label:string;value:unknown}) { return <div><p className="text-xs font-semibold text-slate-500">{label}</p><p className="mt-1 font-extrabold">{String(value)}</p></div>; }

export function AdminApp() {
  const location=useLocation(); const authenticated=!!(localStorage.getItem('pai_admin_key')||sessionStorage.getItem('pai_admin_key'));
  if(location.pathname==='/admin/login') return authenticated?<Navigate to="/admin/ui/dashboard" replace/>:<Login/>;
  return authenticated?<Shell/>:<Navigate to="/admin/login" replace/>;
}
