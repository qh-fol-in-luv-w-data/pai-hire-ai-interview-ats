import { Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { authStore } from '../shared/storage';
import { Button } from '../shared/ui';
import { cn } from '../shared/utils';
import { AuthDialog } from './components/AuthDialog';

const links=[['/apply','Cơ hội nghề nghiệp']] as const;

export function CandidateShell(){
  const [authOpen,setAuthOpen]=useState(false); const [menu,setMenu]=useState(false); const [accountOpen,setAccountOpen]=useState(false); const [,refresh]=useState(0);
  useEffect(()=>{const update=()=>refresh(value=>value+1);window.addEventListener('pai-user-updated',update);return()=>window.removeEventListener('pai-user-updated',update)},[]);
  const user=authStore.user(); const navigate=useNavigate(); const isAdmin=user?.role==='admin'||Boolean(localStorage.getItem('pai_admin_key'));
  const logout=()=>{authStore.clear();setAccountOpen(false);refresh(x=>x+1);navigate('/apply')};
  const accountItems=[
    {to:'/candidate/history?tab=profile',label:'Thông tin tài khoản',note:'Hồ sơ cá nhân'},
    {to:'/candidate/history?tab=apps',label:'Hồ sơ ứng tuyển',note:'Theo dõi tiến trình'},
    ...(isAdmin?[{to:'/admin/ui/dashboard',label:'Trang quản trị',note:'Quản lý tuyển dụng'}]:[]),
  ];
  return <div className="min-h-screen">
    <header className="sticky top-0 z-50 border-b border-slate-200/70 bg-white/85 backdrop-blur-xl">
      <div className="mx-auto flex h-[72px] max-w-[1500px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/apply" className="flex items-center text-navy-950"><span><span className="block font-extrabold leading-none tracking-tight">PAI Tuyển dụng</span><span className="mt-1 block text-[9px] font-extrabold uppercase tracking-[.2em] text-blue-600">Cùng bạn tiến xa</span></span></Link>
        <nav className="hidden rounded-2xl border border-slate-200 bg-slate-50/80 p-1 md:flex">{links.map(([to,label])=><NavLink key={to} to={to} className={({isActive})=>cn('rounded-xl px-4 py-2 text-sm font-extrabold transition',isActive?'bg-white text-navy-950 shadow-sm':'text-slate-500 hover:text-slate-900')}>{label}</NavLink>)}<NavLink to="/candidate/history?tab=profile" className={({isActive})=>cn('rounded-xl px-4 py-2 text-sm font-extrabold transition',isActive?'bg-white text-navy-950 shadow-sm':'text-slate-500 hover:text-slate-900')}>Hồ sơ của tôi</NavLink></nav>
        <div className="hidden items-center gap-2 md:flex"><Link to="/enterprise" className="inline-flex min-h-10 items-center rounded-xl bg-brand-600 px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-brand-700">Dành cho doanh nghiệp</Link>{user?<div className="relative" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setAccountOpen(false)}}><button type="button" onClick={()=>setAccountOpen(!accountOpen)} className={cn('flex items-center gap-2 rounded-2xl border bg-white px-2.5 py-2 text-sm font-extrabold shadow-sm transition',accountOpen?'border-blue-300 ring-4 ring-blue-100':'border-slate-200')}><span className="max-w-32 truncate">{user.name}</span></button>{accountOpen&&<div className="select-menu absolute right-0 top-full mt-2 w-72 rounded-[20px] border border-slate-200 bg-white p-2 shadow-[0_22px_60px_rgba(7,20,38,.2)]"><div className="border-b border-slate-100 px-3 py-3"><p className="truncate text-sm font-extrabold">{user.name}</p><p className="mt-1 truncate text-xs text-slate-500">{user.email||user.phone}</p></div>{accountItems.map(({to,label,note})=>to.startsWith('/admin')?<a key={to} href={to} onClick={()=>setAccountOpen(false)} className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-slate-50"><span><span className="block text-sm font-bold">{label}</span><span className="block text-[11px] text-slate-500">{note}</span></span></a>:<Link key={to} to={to} onClick={()=>setAccountOpen(false)} className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-slate-50"><span><span className="block text-sm font-bold">{label}</span><span className="block text-[11px] text-slate-500">{note}</span></span></Link>)}<button onClick={logout} className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-red-600 hover:bg-red-50"><span className="text-sm font-bold">Đăng xuất</span></button></div>}</div>:<Button onClick={()=>setAuthOpen(true)}>Đăng nhập</Button>}</div>
        <button className="icon-btn md:hidden" onClick={()=>setMenu(!menu)}>{menu?<X/>:<Menu/>}</button>
      </div>
      {menu&&<div className="border-t border-slate-200 bg-white px-4 py-4 md:hidden">{links.map(([to,label])=><Link key={to} className="block rounded-xl px-3 py-3 text-sm font-extrabold text-slate-700" to={to} onClick={()=>setMenu(false)}>{label}</Link>)}<Link to="/enterprise" onClick={()=>setMenu(false)} className="mt-2 block rounded-xl bg-brand-600 px-3 py-3 text-sm font-extrabold text-white">Dành cho doanh nghiệp</Link><Link to="/candidate/history?tab=profile" onClick={()=>setMenu(false)} className="block rounded-xl px-3 py-3 text-sm font-extrabold text-slate-700">Hồ sơ của tôi</Link>{user&&accountItems.map(({to,label})=>to.startsWith('/admin')?<a key={to} href={to} onClick={()=>setMenu(false)} className="flex items-center gap-2 rounded-xl px-3 py-3 text-sm font-bold text-slate-700">{label}</a>:<Link key={to} to={to} onClick={()=>setMenu(false)} className="flex items-center gap-2 rounded-xl px-3 py-3 text-sm font-bold text-slate-700">{label}</Link>)}{user?<button className="mt-2 flex w-full items-center gap-2 rounded-xl bg-red-50 px-3 py-3 text-sm font-extrabold text-red-600" onClick={logout}>Đăng xuất</button>:<button className="btn-primary mt-2 w-full" onClick={()=>setAuthOpen(true)}>Đăng nhập</button>}</div>}
    </header>
    <main><Outlet context={{openAuth:()=>setAuthOpen(true),user}}/></main>
    <footer className="mt-20 bg-navy-950 text-white"><div className="mx-auto grid max-w-[1500px] gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.2fr_.8fr_.8fr] lg:px-8"><div><p className="text-xl font-extrabold">PAI Tuyển dụng</p><p className="mt-3 max-w-md text-sm leading-6 text-slate-400">Một trải nghiệm tuyển dụng liền mạch, minh bạch và tập trung vào năng lực thật của mỗi ứng viên.</p></div><div><p className="eyebrow !text-blue-300">Cam kết</p><p className="mt-3 flex items-center gap-2 text-sm text-slate-300">Bảo vệ dữ liệu ứng viên</p></div><div><p className="eyebrow !text-blue-300">Nền tảng</p><p className="mt-3 flex items-center gap-2 text-sm text-slate-300">Tuyển dụng thông minh</p><p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-slate-600">UI 2026.08 PRO 4</p></div></div></footer>
    <AuthDialog open={authOpen} onClose={()=>setAuthOpen(false)} onSuccess={()=>{setAuthOpen(false);refresh(x=>x+1)}}/>
  </div>;
}
