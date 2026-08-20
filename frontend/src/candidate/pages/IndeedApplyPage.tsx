import { useQuery } from '@tanstack/react-query';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../../shared/api';
import { authStore } from '../../shared/storage';
import type { Job, User } from '../../shared/types';
import { Button, Empty, ErrorState, Loading, SelectField, Success } from '../../shared/ui';
import { positionName, uniquePositions } from '../../shared/utils';

type JobsResponse = { jobs: Job[]; categories: string[] };
type Option = { value: string; label: string };

const levelOptions: Option[] = [
  ['Entry', 'Mới bắt đầu'], ['Junior', 'Nhân viên'], ['Mid', 'Chuyên viên'],
  ['Senior', 'Chuyên viên cao cấp'], ['Manager', 'Quản lý'], ['Director', 'Giám đốc'],
].map(([value, label]) => ({ value, label }));

export function IndeedApplyPage() {
  const { jobId } = useParams();
  return jobId ? <ApplyJobPage jobId={jobId}/> : <ApplyListPage/>;
}

function ApplyListPage() {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [location, setLocation] = useState('');
  const [workType, setWorkType] = useState('');
  const [sort, setSort] = useState('new');
  const [level, setLevel] = useState('Junior');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedId, setSelectedId] = useState('');

  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api<JobsResponse>('/jobs') });
  const all = useMemo(() => uniquePositions(jobs.data?.jobs || []), [jobs.data]);
  const workTypes = useMemo(() => [...new Set(all.map((job) => job.work_type).filter(Boolean) as string[])], [all]);
  const list = useMemo(() => all.filter((job) => (
    (!q || `${positionName(job.title)} ${job.title} ${job.category || ''}`.toLowerCase().includes(q.toLowerCase())) &&
    (!category || job.category === category) && (!location || job.location === location) &&
    (!workType || job.work_type === workType)
  )).sort((a, b) => sort === 'name' ? positionName(a.title).localeCompare(positionName(b.title), 'vi') : 0), [all, q, category, location, workType, sort]);
  const selected = useMemo(() => list.find((job) => job.id === selectedId) || list[0] || null, [list, selectedId]);
  const preview = useQuery({
    queryKey: ['job-preview', selected?.id, level],
    enabled: !!selected,
    queryFn: () => api<Job>(`/jobs/${encodeURIComponent(selected!.id)}?level=${encodeURIComponent(level)}`),
  });
  const previewJob = preview.data || selected;

  useEffect(() => {
    if (!list.length) { setSelectedId(''); return; }
    if (!list.some((job) => job.id === selectedId)) setSelectedId(list[0].id);
  }, [list, selectedId]);

  const reset = () => { setQ(''); setCategory(''); setLocation(''); setWorkType(''); setSort('new'); };

  const filters = <ApplyFilters category={category} setCategory={setCategory} categories={jobs.data?.categories || []} workType={workType} setWorkType={setWorkType} workTypes={workTypes} level={level} setLevel={setLevel} sort={sort} setSort={setSort} reset={reset} />;

  return <div className="min-h-screen bg-[#f7f8fa]">
    <section className="border-b border-blue-950/20 bg-[radial-gradient(circle_at_top_left,_#2f81ed_0,_#123765_45%,_#071426_100%)] text-white">
      <div className="page-container py-8 sm:py-12">
        <div className="flex items-end justify-between gap-5">
          <div><p className="text-sm font-bold text-blue-200">Cơ hội nghề nghiệp</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">Tìm công việc phù hợp với bạn</h1><p className="mt-3 text-sm text-slate-200">Khám phá vị trí đang tuyển và ứng tuyển trực tiếp.</p></div>
        </div>
        <div className="mt-7 grid gap-2 rounded-2xl border border-white/20 bg-white/10 p-2 shadow-xl backdrop-blur md:grid-cols-[1.5fr_1fr_auto]">
          <label className="flex items-center gap-3 rounded-xl bg-slate-50 px-4 ring-1 ring-inset ring-slate-100"><Search className="h-5 w-5 text-slate-400"/><input className="w-full border-0 bg-transparent py-3 text-sm text-slate-900 outline-none" placeholder="Chức danh, kỹ năng hoặc lĩnh vực" value={q} onChange={(event) => setQ(event.target.value)}/></label>
          <label className="flex items-center gap-3 rounded-xl bg-slate-50 px-4 ring-1 ring-inset ring-slate-100"><span className="text-lg text-slate-400">⌖</span><input className="w-full border-0 bg-transparent py-3 text-sm text-slate-900 outline-none" placeholder="Địa điểm" value={location} onChange={(event) => setLocation(event.target.value)}/></label>
          <Button className="min-h-12 px-7" type="button">Tìm việc</Button>
        </div>
      </div>
    </section>
    <div className="page-container">
      <div className="mb-5 flex items-center justify-between"><div><h2 className="section-title">Việc làm đang tuyển</h2><p className="muted mt-1">{list.length} kết quả</p></div><button type="button" onClick={() => setFiltersOpen(true)} className="btn-secondary inline-flex items-center gap-2 lg:hidden"><SlidersHorizontal className="h-4 w-4"/> Bộ lọc</button></div>
      <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="hidden h-fit space-y-5 lg:block">{filters}</aside>
        <div>
          {jobs.isLoading ? <Loading/> : jobs.error ? <ErrorState message={(jobs.error as Error).message}/> : !list.length ? <Empty title="Không tìm thấy việc phù hợp" description="Hãy thử thay đổi bộ lọc hoặc từ khóa."/> :
            <div className="grid gap-4 xl:grid-cols-[430px_minmax(0,1fr)]">
              <div className="space-y-3 xl:max-h-[calc(100vh-160px)] xl:overflow-y-auto xl:pr-1">
                {list.map((job) => <JobTile key={job.id} job={job} level={level} selected={job.id === selected?.id} onSelect={() => setSelectedId(job.id)}/>)}
              </div>
              <JobPreview job={previewJob} loading={preview.isLoading} error={preview.error} level={level}/>
            </div>}
        </div>
      </div>
    </div>
    {filtersOpen && <div className="fixed inset-0 z-[170] bg-slate-950/55 p-4 lg:hidden"><button className="absolute inset-0" aria-label="Đóng bộ lọc" onClick={() => setFiltersOpen(false)}/><section className="relative mx-auto mt-10 max-w-md rounded-3xl bg-white p-6 shadow-2xl"><div className="flex items-center justify-between"><h2 className="text-lg font-extrabold">Bộ lọc việc làm</h2><button className="icon-btn" onClick={() => setFiltersOpen(false)}><X/></button></div><div className="mt-6 space-y-5">{filters}</div><Button className="mt-6 w-full" onClick={() => setFiltersOpen(false)}>Xem {list.length} việc làm</Button></section></div>}
  </div>;
}

function ApplyJobPage({ jobId }: { jobId: string }) {
  const [searchParams] = useSearchParams();
  const { openAuth, user } = useOutletContext<{ openAuth: () => void; user: User | null }>();
  const [level, setLevel] = useState(searchParams.get('level') || 'Junior');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null!);
  const detail = useQuery({
    queryKey: ['job-detail', jobId, level],
    queryFn: () => api<Job>(`/jobs/${encodeURIComponent(jobId)}?level=${encodeURIComponent(level)}`),
  });
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!user) { openAuth(); return; }
    const form = new FormData(event.currentTarget);
    form.set('name', user.name); form.set('email', user.email || ''); form.set('phone', user.phone || ''); form.set('level', level);
    setSending(true); setError('');
    try {
      await api(`/jobs/${encodeURIComponent(jobId)}/apply`, { method: 'POST', headers: { Authorization: `Bearer ${authStore.token()}` }, body: form });
      setSubmitted(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Không thể nộp hồ sơ'); } finally { setSending(false); }
  };
  const active = detail.data || null;

  useEffect(() => { setSubmitted(false); setError(''); }, [jobId]);

  return <div className="min-h-screen bg-[#f7f8fa]">
    <section className="border-b border-slate-200 bg-white">
      <div className="page-container py-6">
        <Link to="/apply" className="text-sm font-extrabold text-brand-700">Quay lại danh sách việc làm</Link>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-bold text-brand-700">Chi tiết vị trí</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-950">{positionName(active?.title)}</h1>
            <p className="mt-2 text-sm text-slate-500">CT Group · {active?.location || 'TP. Hồ Chí Minh'} · {active?.work_type || 'Toàn thời gian'}</p>
          </div>
          <a href="#apply-form" className="btn-primary inline-flex min-h-12 items-center justify-center px-6">Ứng tuyển ngay</a>
        </div>
      </div>
    </section>
    <div className="page-container">
      {detail.isLoading ? <Loading/> : detail.error ? <ErrorState message={(detail.error as Error).message}/> :
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <main className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            <div className="flex flex-wrap gap-2 text-xs font-bold text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-1.5">{active?.category || 'Tuyển dụng'}</span>
              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700">{active?.salary_range || 'Theo khung thị trường'}</span>
              <span className="rounded-full bg-blue-50 px-3 py-1.5 text-blue-700">{active?.work_type || 'Toàn thời gian'}</span>
            </div>
            <div className="mt-8"><h2 className="text-xl font-extrabold text-slate-950">Mô tả công việc</h2><JobDescription content={active?.jd_content || ''}/></div>
          </main>
          <aside id="apply-form" className="h-fit rounded-3xl border border-slate-200 bg-white p-5 shadow-sm lg:sticky lg:top-24">
            <h2 className="text-lg font-extrabold text-slate-950">Nộp hồ sơ</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">Tải CV lên để hệ thống ghi nhận hồ sơ và HR theo dõi tiến trình.</p>
            {submitted ? <div className="mt-5"><Success title="Đã nhận hồ sơ" description="Bạn có thể theo dõi tiến trình trong Hồ sơ của tôi."/></div> : <form className="mt-5 space-y-4" onSubmit={submit}>
              <Select label="Cấp bậc" value={level} onChange={setLevel} options={levelOptions}/>
              <label className="block cursor-pointer rounded-2xl border-2 border-dashed border-slate-300 p-5 text-center">
                <span className="text-sm font-bold">Chọn CV PDF hoặc DOCX</span>
                <input ref={fileRef} name="cv_file" type="file" accept=".pdf,.doc,.docx" className="mt-3 w-full text-xs" required/>
              </label>
              {error && <p className="text-sm font-bold text-red-700">{error}</p>}
              <Button disabled={sending} className="w-full" onClick={() => { if (!user) openAuth(); }}>{sending ? 'Đang gửi...' : user ? 'Nộp hồ sơ' : 'Đăng nhập để nộp hồ sơ'}</Button>
            </form>}
          </aside>
        </div>}
    </div>
  </div>;
}

function JobTile({ job, level, selected, onSelect }: { job: Job; level: string; selected: boolean; onSelect: () => void }) {
  return <article className={`rounded-2xl border bg-white p-5 text-left shadow-sm transition hover:border-blue-400 hover:shadow-md ${selected ? 'border-blue-500 ring-4 ring-blue-100/80' : 'border-slate-200'}`}>
    <button type="button" onClick={onSelect} className="block w-full text-left">
      <div className="flex items-start justify-between gap-3"><div><h3 className="text-lg font-extrabold text-slate-950">{positionName(job.title)}</h3><p className="mt-1 text-sm text-slate-600">CT Group · {job.location || 'TP. Hồ Chí Minh'}</p></div><span className="text-xs font-bold text-emerald-700">Đang tuyển</span></div>
      <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold text-slate-500"><span>{job.work_type || 'Toàn thời gian'}</span><span>·</span><span className="text-emerald-700">{job.salary_range || 'Theo khung thị trường'}</span></div>
      <p className="mt-4 line-clamp-2 text-sm leading-6 text-slate-500">{job.jd_content?.replace(/[#*_]/g, '').slice(0, 160) || 'Xem mô tả và yêu cầu công việc.'}</p>
    </button>
    <Link to={`/apply/${encodeURIComponent(job.id)}?level=${encodeURIComponent(level)}`} className="mt-4 inline-flex text-sm font-extrabold text-brand-700 xl:hidden">Xem chi tiết và ứng tuyển</Link>
  </article>;
}

function JobPreview({ job, loading, error, level }: { job: Job | null; loading: boolean; error: unknown; level: string }) {
  if (!job) return <div className="hidden min-h-[520px] rounded-2xl border border-slate-200 bg-white xl:block"><Empty title="Chọn một vị trí" description="JD sẽ hiển thị tại đây."/></div>;
  return <section className="hidden h-fit max-h-[calc(100vh-160px)] overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-sm xl:sticky xl:top-24 xl:block">
    <div className="sticky top-0 z-10 border-b border-slate-100 bg-white/95 p-6 backdrop-blur">
      <p className="text-xs font-extrabold uppercase tracking-wide text-brand-700">Xem nhanh JD</p>
      <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-slate-950">{positionName(job.title)}</h2>
      <p className="mt-2 text-sm text-slate-500">CT Group · {job.location || 'TP. Hồ Chí Minh'} · {job.work_type || 'Toàn thời gian'}</p>
      <Link to={`/apply/${encodeURIComponent(job.id)}?level=${encodeURIComponent(level)}`} className="btn-primary mt-5 inline-flex min-h-11 items-center justify-center px-5">Ứng tuyển vị trí này</Link>
    </div>
    <div className="p-6">
      {loading ? <Loading/> : error ? <ErrorState message={(error as Error).message}/> : <>
        <div className="flex flex-wrap gap-2 text-xs font-bold text-slate-600">
          <span className="rounded-full bg-slate-100 px-3 py-1.5">{job.category || 'Tuyển dụng'}</span>
          <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700">{job.salary_range || 'Theo khung thị trường'}</span>
          <span className="rounded-full bg-blue-50 px-3 py-1.5 text-blue-700">{job.work_type || 'Toàn thời gian'}</span>
        </div>
        <JobDescription content={job.jd_content || ''}/>
      </>}
    </div>
  </section>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Option[] }) {
  return <div><span className="label">{label}</span><SelectField value={value} onChange={onChange} options={options}/></div>;
}
function ApplyFilters({ category, setCategory, categories, workType, setWorkType, workTypes, level, setLevel, sort, setSort, reset }: { category: string; setCategory: (value: string) => void; categories: string[]; workType: string; setWorkType: (value: string) => void; workTypes: string[]; level: string; setLevel: (value: string) => void; sort: string; setSort: (value: string) => void; reset: () => void }) {
  return <><Select label="Lĩnh vực" value={category} onChange={setCategory} options={[{ value: '', label: 'Tất cả lĩnh vực' }, ...categories.map((item) => ({ value: item, label: item }))]}/><Select label="Hình thức" value={workType} onChange={setWorkType} options={[{ value: '', label: 'Tất cả hình thức' }, ...workTypes.map((item) => ({ value: item, label: item }))]}/><Select label="Cấp bậc" value={level} onChange={setLevel} options={levelOptions}/><Select label="Sắp xếp" value={sort} onChange={setSort} options={[{ value: 'new', label: 'Mới cập nhật' }, { value: 'name', label: 'Tên A-Z' }]}/><button type="button" onClick={reset} className="text-sm font-bold text-brand-700">Xóa bộ lọc</button></>;
}

function JobDescription({ content }: { content: string }) {
  const lines = content.split('\n').map((line) => line.trim()).filter(Boolean);
  return <div className="mt-4 space-y-3 text-sm leading-7 text-slate-600">{(lines.length ? lines : ['Chưa có mô tả công việc.']).map((line, index) => line.startsWith('#') ? <h4 key={index} className="pt-2 font-extrabold text-slate-900">{line.replace(/^#+\s*/, '')}</h4> : <p key={index} className={/^[-*•]/.test(line) ? 'border-l-2 border-blue-200 pl-3' : ''}>{line.replace(/^[-*•]\s*/, '').replace(/\*\*/g, '')}</p>)}</div>;
}
