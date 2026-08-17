import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { api, jsonInit } from '../../shared/api';
import { authStore } from '../../shared/storage';
import { statusLabel, statusTone } from '../../shared/status';
import type { User } from '../../shared/types';
import { Badge, Button, Card, Empty, ErrorState, Loading } from '../../shared/ui';
import { formatDate, levelName, positionName } from '../../shared/utils';

type CandidateApplication = {
  id: string; job_id: string; cv_filename?: string; cv_score?: number | null;
  status: string; applied_at: string; level?: string;
  application_logs?: { id?: number|string; message: string; created_at?: string }[];
};
type CandidateAnswer = {
  question_number: string; question_text?: string; transcript?: string;
  duration_sec?: number; time_spent?: number;
};
type CandidateAlert = { alert_type?: string; count?: number; duration_seconds?: number; timestamp?: string };
type CandidateInterview = {
  id: string; position_id: string; level?: string; status: string; submitted_at?: string;
  tab_switches?: number; answers?: CandidateAnswer[];
  proctoring_logs?: { tab_switches?: number; proctoring_alerts?: CandidateAlert[] };
};
type History = { applications: CandidateApplication[]; interviews: CandidateInterview[] };

const alertLabels: Record<string, string> = {
  NO_FACE: 'Không phát hiện khuôn mặt',
  MULTIPLE_FACES: 'Phát hiện nhiều khuôn mặt',
  MULTI_FACE: 'Phát hiện nhiều khuôn mặt',
  TAB_SWITCH: 'Rời khỏi tab phỏng vấn',
  PHONE_DETECTED: 'Phát hiện thiết bị không phù hợp',
  LOOKING_AWAY: 'Nhìn ra ngoài khung hình',
  CAMERA_BLOCKED: 'Camera bị che hoặc gián đoạn',
  AUDIO_ANOMALY: 'Âm thanh bất thường',
  TIME_LAPSE: 'Hình ảnh camera bị gián đoạn',
  SPOOFING: 'Nghi ngờ hình ảnh không hợp lệ',
};

function alertLabel(type?: string) {
  return alertLabels[(type || '').toUpperCase()] || 'Cảnh báo giám sát khác';
}

function groupAlerts(alerts: CandidateAlert[]) {
  const groups = new Map<string, CandidateAlert & { total: number }>();
  for (const alert of alerts) {
    const key = (alert.alert_type || 'OTHER').toUpperCase();
    const current = groups.get(key);
    const amount = Number(alert.count) > 0 ? Number(alert.count) : 1;
    if (current) {
      current.total += amount;
      current.duration_seconds = (current.duration_seconds || 0) + (alert.duration_seconds || 0);
      if ((alert.timestamp || '') > (current.timestamp || '')) current.timestamp = alert.timestamp;
    } else groups.set(key, { ...alert, alert_type: key, total: amount });
  }
  return [...groups.values()];
}

function duration(seconds?: number) {
  if (!seconds || seconds < 1) return '';
  const minutes = Math.floor(seconds / 60);
  const remain = Math.round(seconds % 60);
  return minutes ? `${minutes} phút ${remain} giây` : `${remain} giây`;
}

export function HistoryPage() {
  const { openAuth, user } = useOutletContext<{ openAuth: () => void; user: User | null }>();
  const [params, setParams] = useSearchParams();
  const [expanded, setExpanded] = useState<string[]>([]);
  const tab = params.get('tab') || 'apps';
  const query = useQuery({
    queryKey: ['history', user?.email, user?.phone],
    enabled: !!user,
    queryFn: () => api<History>('/auth/history', { headers: { Authorization: `Bearer ${authStore.token()}` } }),
  });

  if (!user) return <div className="page-container"><Card className="mx-auto max-w-lg p-8 text-center"><h1 className="text-xl font-extrabold">Đăng nhập để xem hồ sơ</h1><p className="mt-2 text-sm text-slate-500">Lịch sử ứng tuyển và bài phỏng vấn được lưu trong tài khoản của bạn.</p><button className="btn-primary mt-5" onClick={openAuth}>Đăng nhập</button></Card></div>;

  const selectTab = (value: string) => { setExpanded([]); setParams({ tab: value }); };
  return <div className="page-container">
    <section className="hero-mesh overflow-hidden rounded-[30px] p-6 text-white shadow-[0_24px_65px_rgba(7,20,38,.22)] sm:p-9">
      <p className="text-sm text-blue-200">Hồ sơ của tôi</p>
      <h1 className="mt-1 text-2xl font-extrabold sm:text-3xl">Xin chào, {user.name}</h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-300">Theo dõi tiến trình, điểm CV và xem lại nội dung bạn đã thực hiện trong phỏng vấn.</p>
    </section>
    <div className="mt-6 inline-flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm">
      {([['apps', 'Hồ sơ ứng tuyển'], ['interviews', 'Bài phỏng vấn'], ['profile', 'Tài khoản']] as const).map(([value, label]) => <button key={value} className={`px-4 py-3 text-sm font-bold ${tab === value ? 'rounded-xl bg-navy-950 text-white shadow-md' : 'rounded-xl text-slate-500 hover:bg-slate-100'}`} onClick={() => selectTab(value)}>{label}</button>)}
    </div>
    {tab === 'profile' && <ProfileEditor user={user} />}
    {query.isLoading ? <Loading /> : query.error ? <ErrorState message={(query.error as Error).message} retry={() => query.refetch()} /> : tab === 'apps' ? <Applications applications={query.data?.applications || []} /> : tab === 'interviews' ? <Interviews interviews={query.data?.interviews || []} expanded={expanded} setExpanded={setExpanded} /> : null}
  </div>;
}

function ProfileEditor({ user }: { user: User }) {
  const [name, setName] = useState(user.name || '');
  const [email, setEmail] = useState(user.email || '');
  const [phone, setPhone] = useState(user.phone || '');
  const [message, setMessage] = useState('');
  const save = async (event: FormEvent) => {
    event.preventDefault(); setMessage('');
    try {
      const result = await api<{ user: User }>('/auth/profile', { ...jsonInit('PATCH', { name, email, phone }), headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authStore.token()}` } });
      authStore.save(result.user, authStore.token() || result.user.id || ''); window.dispatchEvent(new Event('pai-user-updated')); setMessage('Đã lưu thông tin tài khoản.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không thể lưu thông tin'); }
  };
  return <Card className="mt-5 p-6"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Tài khoản</p><h2 className="section-title mt-2">Chỉnh sửa thông tin</h2><p className="mt-1 text-sm text-slate-500">Cập nhật thông tin liên hệ để nhận thông báo tuyển dụng chính xác.</p></div></div><form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={save}><label><span className="label">Họ và tên</span><input className="field" value={name} onChange={event => setName(event.target.value)} required /></label><label><span className="label">Email</span><input className="field" type="email" value={email} onChange={event => setEmail(event.target.value)} required /></label><label><span className="label">Số điện thoại</span><input className="field" value={phone} onChange={event => setPhone(event.target.value)} /></label><div className="flex items-end justify-end"><Button type="submit">Lưu thay đổi</Button></div></form>{message && <p className="mt-4 rounded-xl bg-emerald-50 p-3 text-sm font-semibold text-emerald-700">{message}</p>}</Card>;
}

function Applications({ applications }: { applications: CandidateApplication[] }) {
  if (!applications.length) return <div className="mt-5"><Empty title="Bạn chưa nộp hồ sơ" description="Khám phá các vị trí đang tuyển để bắt đầu." /></div>;
  return <div className="mt-5 space-y-4">{applications.map(app => <Card key={app.id} className="p-5"><div><h3 className="font-extrabold">{positionName(app.job_id)}</h3><p className="mt-1 text-xs text-slate-500">{levelName(app.level)} · Nộp {formatDate(app.applied_at)}{app.cv_filename ? ` · ${app.cv_filename}` : ''}</p></div>{app.application_logs?.length ? <div className="mt-5 border-t pt-4"><p className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">Tiến trình hồ sơ</p>{app.application_logs.slice(0, 4).map((log, i) => <div key={String(log.id || i)} className="relative flex gap-3 pb-3 last:pb-0"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" /><div><p className="text-sm font-semibold text-slate-700">{log.message}</p><p className="text-xs text-slate-400">{formatDate(log.created_at)}</p></div></div>)}</div> : null}</Card>)}</div>;
}

function Interviews({ interviews, expanded, setExpanded }: { interviews: CandidateInterview[]; expanded: string[]; setExpanded: (updater: (previous: string[]) => string[]) => void }) {
  if (!interviews.length) return <div className="mt-5"><Empty title="Chưa có bài phỏng vấn" /></div>;
  return <div className="mt-5 grid gap-4 lg:grid-cols-2">{interviews.map(iv => {
    const alerts = iv.proctoring_logs?.proctoring_alerts || [];
    const switches = iv.proctoring_logs?.tab_switches ?? iv.tab_switches ?? 0;
    const alertGroups = groupAlerts(alerts);
    const isOpen = expanded.includes(iv.id);
    return <Card key={iv.id} className="p-5"><div className="flex justify-between gap-3"><div><h3 className="font-extrabold">{positionName(iv.position_id)}</h3><p className="mt-1 text-xs text-slate-500">{levelName(iv.level)} · Nộp {formatDate(iv.submitted_at)}</p></div><Badge tone={statusTone(iv.status)}>{statusLabel(iv.status)}</Badge></div><div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-sm"><div><p className="text-xs text-slate-500">Câu đã trả lời</p><p className="font-bold">{iv.answers?.length || 0}</p></div><div><p className="text-xs text-slate-500">Chuyển tab</p><p className="font-bold">{switches} lần</p></div></div><div className="mt-4 flex flex-wrap items-center gap-2 text-xs font-semibold"><span className={`rounded-full px-3 py-1.5 ${alertGroups.length ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>{alertGroups.length ? `${alertGroups.length} loại cảnh báo giám sát` : 'Không có cảnh báo giám sát'}</span><button className="ml-auto rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-brand-700 hover:bg-blue-50" onClick={() => setExpanded(previous => previous.includes(iv.id) ? previous.filter(value => value !== iv.id) : [...previous, iv.id])}>{isOpen ? 'Thu gọn' : 'Xem câu hỏi và câu trả lời'}</button></div>{isOpen && <div className="mt-5 space-y-4 border-t pt-5"><div><h4 className="font-extrabold">Nội dung phỏng vấn</h4><p className="mt-1 text-xs text-slate-500">Đây là nội dung bạn đã nghe và câu trả lời đã ghi nhận. Nhận xét, điểm đánh giá nội bộ không hiển thị tại đây.</p></div>{iv.answers?.length ? iv.answers.map((answer, index) => <div key={`${iv.id}-${answer.question_number}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs font-extrabold uppercase tracking-wide text-brand-700">Câu {answer.question_number || index + 1}</p><p className="mt-2 text-sm font-bold leading-6 text-slate-900">{answer.question_text || 'Không có nội dung câu hỏi'}</p><div className="mt-3 rounded-xl bg-slate-50 p-3 text-sm leading-6 text-slate-700"><p className="mb-1 text-xs font-bold text-slate-500">Câu trả lời của bạn</p>{answer.transcript?.trim() || 'Không ghi nhận được nội dung trả lời bằng văn bản.'}</div>{duration(answer.duration_sec || answer.time_spent) && <p className="mt-2 text-xs text-slate-400">Thời lượng: {duration(answer.duration_sec || answer.time_spent)}</p>}</div>) : <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Chưa có bản ghi câu trả lời chi tiết.</p>}<div className="rounded-2xl border border-slate-200 p-4"><h4 className="font-extrabold">Thông tin giám sát</h4><p className="mt-2 text-sm text-slate-600">Đã rời tab: <strong>{switches} lần</strong></p>{alertGroups.length ? <div className="mt-3 space-y-2">{alertGroups.map(alert => <div key={alert.alert_type} className="flex justify-between gap-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800"><span>{alertLabel(alert.alert_type)}</span><strong>{alert.total} lần</strong></div>)}</div> : <p className="mt-2 text-sm text-emerald-700">Không ghi nhận cảnh báo khác.</p>}</div></div>}</Card>;
  })}</div>;
}
