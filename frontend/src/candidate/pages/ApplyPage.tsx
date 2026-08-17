import { useQuery } from '@tanstack/react-query';
import { LoaderCircle, Search, X } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { api } from '../../shared/api';
import { authStore } from '../../shared/storage';
import type { Job, User } from '../../shared/types';
import { Button, Card, Empty, ErrorState, Loading, SelectField, Success } from '../../shared/ui';
import { positionName, stripPositionLevel, uniquePositions } from '../../shared/utils';

type JobsResponse={jobs:Job[];categories:string[]};
const levels=['Entry','Junior','Mid','Senior','Manager','Director'];
const levelLabels:Record<string,string>={Entry:'Mới bắt đầu',Junior:'Nhân viên',Mid:'Chuyên viên',Senior:'Chuyên viên cao cấp',Manager:'Quản lý',Director:'Giám đốc'};
const levelOptions=levels.map(value=>({value,label:levelLabels[value]}));

export function ApplyPage(){
  const {jobId}=useParams();
  const {openAuth,user}=useOutletContext<{openAuth:()=>void;user:User|null}>();
  const [search,setSearch]=useState('');
  const [searchOpen,setSearchOpen]=useState(false);
  const [category,setCategory]=useState('');
  const [locationFilter,setLocationFilter]=useState('');
  const [workType,setWorkType]=useState('');
  const [sort,setSort]=useState('name');
  const [selected,setSelected]=useState<Job|null>(null);
  const [level,setLevel]=useState('Junior');
  const [submitted,setSubmitted]=useState(false);
  const [sending,setSending]=useState(false);
  const [error,setError]=useState('');
  const fileRef=useRef<HTMLInputElement>(null);
  const jobs=useQuery({queryKey:['jobs'],queryFn:()=>api<JobsResponse>('/jobs')});
  const allJobs=useMemo(()=>uniquePositions(jobs.data?.jobs||[]),[jobs.data]);
  const locations=useMemo(()=>[...new Set(allJobs.map(j=>j.location).filter(Boolean) as string[])],[allJobs]);
  const workTypes=useMemo(()=>[...new Set(allJobs.map(j=>j.work_type).filter(Boolean) as string[])],[allJobs]);
  const list=useMemo(()=>{
    const filtered=allJobs.filter(j=>
      (!category||j.category===category)&&
      (!locationFilter||j.location===locationFilter)&&
      (!workType||j.work_type===workType)&&
      (!search||(positionName(j.title)+' '+j.title+' '+(j.category||'')).toLowerCase().includes(search.toLowerCase()))
    );
    return [...filtered].sort((a,b)=>sort==='name-desc'
      ?positionName(b.title).localeCompare(positionName(a.title),'vi')
      :positionName(a.title).localeCompare(positionName(b.title),'vi'));
  },[allJobs,category,locationFilter,workType,search,sort]);
  const suggestions=useMemo(()=>search.trim()?allJobs.filter(job=>(positionName(job.title)+' '+job.title).toLowerCase().includes(search.toLowerCase())).slice(0,6):[],[allJobs,search]);
  const jobAtLevel=(job:Job)=>(jobs.data?.jobs||[]).find(item=>stripPositionLevel(item.id)===stripPositionLevel(job.id)&&item.id.startsWith(level+'_'))||job;
  useEffect(()=>{
    if(jobId&&jobs.data&&!selected){
      const match=jobs.data.jobs.find(j=>j.id===jobId);
      if(match)setSelected(match);
    }
  },[jobId,jobs.data,selected]);
  const detail=useQuery({
    queryKey:['job-detail',selected?.id,level],
    enabled:!!selected,
    queryFn:()=>api<Job>('/jobs/'+encodeURIComponent(selected!.id)+'?level='+encodeURIComponent(level)),
  });
  const activeJob=detail.data||selected;
  const resetFilters=()=>{setCategory('');setLocationFilter('');setWorkType('');setSort('name');setSearch('')};
  const submit=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();
    if(!user){openAuth();return}
    if(!selected)return;
    const fd=new FormData(e.currentTarget);
    fd.set('name',user.name||String(fd.get('name')||''));
    fd.set('email',user.email||String(fd.get('email')||''));
    fd.set('phone',user.phone||String(fd.get('phone')||''));
    fd.set('level',level);
    setSending(true);setError('');
    try{
      await api('/jobs/'+encodeURIComponent(selected.id)+'/apply',{method:'POST',headers:{Authorization:`Bearer ${authStore.token()}`},body:fd});
      localStorage.setItem('pai_candidate_last_lookup',JSON.stringify({name:user.name,email:user.email,phone:user.phone}));
      setSubmitted(true);
    }catch(e){setError(e instanceof Error?e.message:'Không thể nộp hồ sơ')}
    finally{setSending(false)}
  };
  return <>
    <section className="hero-mesh relative z-30 !overflow-visible text-white">
      <div className="page-container py-10 sm:py-14">
        <div className="max-w-3xl">
          <span className="inline-flex rounded-full bg-brand-500/20 px-3 py-1 text-xs font-bold text-blue-200">Cơ hội nghề nghiệp tại CT Group</span>
          <h1 className="mt-4 text-3xl font-extrabold leading-tight tracking-[-.04em] sm:text-5xl">Nơi năng lực của bạn<br className="hidden sm:block"/> được nhìn thấy.</h1>
          <p className="mt-4 max-w-2xl text-slate-300">Nộp CV trực tuyến, theo dõi tiến trình và tham gia phỏng vấn trong cùng một hệ thống.</p>
        </div>
        <div className="relative z-20 mt-8 block max-w-3xl">
          <Search className="absolute left-4 top-3.5 h-5 w-5 text-slate-400"/>
          <input className="w-full rounded-2xl border-0 bg-white py-3.5 pl-12 pr-4 text-slate-900 shadow-lg placeholder:text-slate-400 focus:ring-4 focus:ring-brand-500/20" placeholder="Tìm theo tên vị trí hoặc lĩnh vực..." value={search} onFocus={()=>setSearchOpen(true)} onBlur={()=>setTimeout(()=>setSearchOpen(false),120)} onChange={e=>{setSearch(e.target.value);setSearchOpen(true)}}/>
          {searchOpen&&suggestions.length>0&&<div className="select-menu absolute inset-x-0 top-full mt-3 overflow-hidden rounded-[20px] border border-slate-200 bg-white p-2 text-slate-900 shadow-[0_24px_65px_rgba(7,20,38,.32)]">{suggestions.map(job=><button type="button" key={job.id} className="flex w-full items-center justify-between rounded-[14px] px-4 py-3 text-left transition hover:bg-blue-50" onMouseDown={()=>{setSelected(job);setSearch(positionName(job.title));setSearchOpen(false)}}><span><span className="block text-sm font-extrabold">{positionName(job.title)}</span><span className="mt-1 block text-xs text-slate-500">{job.category||'Khối chuyên môn'}</span></span><span className="text-xs font-bold text-blue-600">Xem vị trí</span></button>)}</div>}
        </div>
      </div>
    </section>
    <div className="page-container">
      <Card className="relative z-40 mb-6 overflow-visible p-4 sm:p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-extrabold">Bộ lọc việc làm</h2>
          <button className="text-sm font-bold text-brand-700 hover:underline" onClick={resetFilters}>Xóa bộ lọc</button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Filter label="Lĩnh vực" value={category} onChange={setCategory} all="Tất cả lĩnh vực" items={jobs.data?.categories||[]}/>
          <Filter label="Địa điểm" value={locationFilter} onChange={setLocationFilter} all="Tất cả địa điểm" items={locations}/>
          <Filter label="Hình thức làm việc" value={workType} onChange={setWorkType} all="Tất cả hình thức" items={workTypes}/>
          <div><span className="label">Cấp bậc ứng tuyển</span><SelectField value={level} onChange={setLevel} options={levelOptions}/></div>
          <div><span className="label">Sắp xếp</span><SelectField value={sort} onChange={setSort} options={[{value:'name',label:'Tên A–Z'},{value:'name-desc',label:'Tên Z–A'}]}/></div>
        </div>
      </Card>
      <div className="mb-5"><h2 className="section-title">Vị trí đang tuyển</h2><p className="muted mt-1">{list.length} cơ hội phù hợp</p></div>
      {jobs.isLoading?<Loading/>:jobs.error?<ErrorState message={(jobs.error as Error).message} retry={()=>jobs.refetch()}/>:!list.length?<Empty title="Không tìm thấy vị trí phù hợp" description="Hãy thử xóa bớt bộ lọc hoặc dùng từ khóa khác."/>:
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{list.map(job=>
          <Card key={job.id} className="group flex flex-col p-5 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg">
            <div className="flex items-center justify-between gap-3">
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-brand-700">{job.category||'Khối chuyên môn'}</span>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-700">Đang tuyển</span>
            </div>
            <h3 className="mt-5 text-lg font-extrabold leading-7 text-slate-950">{positionName(job.title)}</h3>
            <div className="mt-4 space-y-2 text-sm text-slate-600">
              <p>{job.location||'TP. Hồ Chí Minh'}</p>
              <p>{job.work_type||'Toàn thời gian'}</p>
              <p className="font-bold text-emerald-700">{jobAtLevel(job).salary_range||'Theo khung thị trường'}</p>
            </div>
            <Button className="mt-5 w-full" onClick={()=>{setSelected(job);setSubmitted(false);setError('')}}>Xem chi tiết và ứng tuyển</Button>
          </Card>)}
        </div>}
    </div>
    {selected&&<div className="fixed inset-0 z-[150] overflow-y-auto bg-navy-950/60 p-3 backdrop-blur-[6px] sm:p-6">
      <div className="modal-enter mx-auto max-w-5xl overflow-hidden rounded-[30px] border border-white/80 bg-white shadow-[0_35px_100px_rgba(7,20,38,.4)]">
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-100 bg-white/90 px-5 py-5 backdrop-blur-xl sm:px-7">
          <div><p className="text-xs font-bold uppercase text-brand-700">Vị trí ứng tuyển</p><h2 className="mt-1 text-xl font-extrabold">{positionName(activeJob?.title||selected.title)}</h2></div>
          <button className="icon-btn border border-slate-200 bg-white shadow-sm" onClick={()=>setSelected(null)} aria-label="Đóng"><X/></button>
        </header>
        {submitted?<div className="p-8"><Success title="Đã nhận hồ sơ" description="Hệ thống đang đánh giá CV. Bạn có thể theo dõi tiến trình trong mục Hồ sơ của tôi."/><div className="flex justify-center"><a className="btn-primary" href="/candidate/history?tab=apps">Xem tiến trình ứng tuyển</a></div></div>:
          <div className="grid md:grid-cols-[1.3fr_.7fr]">
            <div className="border-b p-6 md:border-b-0 md:border-r sm:p-8">
              <h3 className="font-extrabold">Mô tả công việc</h3>
              {detail.isLoading?<Loading label="Đang tải mô tả công việc..."/>:detail.error?<ErrorState message={detail.error.message} retry={()=>detail.refetch()}/>:<JobDescription content={activeJob?.jd_content||''}/>}
            </div>
            <form className="space-y-4 p-6 sm:p-8" onSubmit={submit}>
              <h3 className="font-extrabold">Thông tin ứng tuyển</h3>
              <div><span className="label">Cấp bậc</span><SelectField value={level} onChange={setLevel} options={levelOptions}/></div>
              <label><span className="label">Họ và tên</span><input name="name" className="field" defaultValue={user?.name||''} required/></label>
              <label><span className="label">Email</span><input name="email" type="email" className="field" defaultValue={user?.email||''} required/></label>
              <label><span className="label">Số điện thoại</span><input name="phone" className="field" defaultValue={user?.phone||''}/></label>
              <label className="block cursor-pointer rounded-2xl border-2 border-dashed border-slate-300 p-5 text-center hover:border-brand-500"><span className="block text-sm font-bold">Chọn CV PDF hoặc DOCX</span><input ref={fileRef} name="cv_file" type="file" accept=".pdf,.doc,.docx" className="mt-3 w-full text-xs" required/></label>
              {error&&<p className="rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p>}
              <Button className="w-full" disabled={sending||detail.isLoading}>{sending&&<LoaderCircle className="h-4 w-4 animate-spin"/>}{user?'Nộp hồ sơ':'Đăng nhập để nộp hồ sơ'}</Button>
            </form>
          </div>}
      </div>
    </div>}
  </>;
}

function Filter({label,value,onChange,all,items}:{label:string;value:string;onChange:(value:string)=>void;all:string;items:string[]}){
  return <div><span className="label">{label}</span><SelectField value={value} onChange={onChange} options={[{value:'',label:all},...items.map(item=>({value:item,label:item}))]}/></div>;
}

function JobDescription({content}:{content:string}){
  const lines=content.split('\n').map(line=>line.trim()).filter(Boolean);
  if(!lines.length)return <Empty title="Chưa có mô tả công việc" description="Đội tuyển dụng đang cập nhật nội dung cho vị trí này."/>;
  return <div className="mt-5 max-h-[65vh] space-y-3 overflow-y-auto pr-2 text-sm leading-7 text-slate-600">{lines.map((line,index)=>{
    if(line.startsWith('#'))return <h4 key={index} className="pt-2 text-base font-extrabold text-slate-900">{line.replace(/^#+\s*/,'')}</h4>;
    if(/^[-*•]\s+/.test(line))return <p key={index} className="border-l-2 border-blue-200 pl-3"><span>{line.replace(/^[-*•]\s+/,'')}</span></p>;
    return <p key={index}>{line.replace(/\*\*/g,'')}</p>;
  })}</div>;
}
