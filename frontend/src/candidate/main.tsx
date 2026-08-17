import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import '../styles.css';
import { CandidateShell } from './shell';
import { IndeedApplyPage } from './pages/IndeedApplyPage';
import { HistoryPage } from './pages/HistoryPage';
import { ReplyPage } from './pages/ReplyPage';
import { EnterprisePage } from './pages/EnterprisePage';
import { EnterpriseRegisterPage } from './pages/EnterpriseRegisterPage';
import { EnterprisePortalPage } from './pages/EnterprisePortalPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } } });
class EnterpriseErrorBoundary extends Component<{children:ReactNode},{error?:Error}>{
  state:{error?:Error}={};
  static getDerivedStateFromError(error:Error){return {error};}
  componentDidCatch(_error:Error,_info:ErrorInfo){}
  render(){return this.state.error?<main className="page-container py-12"><section className="mx-auto max-w-xl rounded-3xl border border-red-200 bg-white p-7 shadow-sm"><p className="text-sm font-extrabold text-red-700">Không thể hiển thị khu vực doanh nghiệp</p><p className="mt-2 text-sm leading-6 text-slate-600">{this.state.error.message||'Đã có lỗi không xác định.'}</p><button className="btn-primary mt-6" onClick={()=>location.reload()}>Tải lại trang</button></section></main>:this.props.children;}
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><EnterpriseErrorBoundary><Routes><Route path="/enterprise" element={<EnterprisePage/>}/><Route path="/enterprise/register" element={<EnterpriseRegisterPage/>}/><Route path="/enterprise/portal" element={<EnterprisePortalPage/>}/><Route path="/enterprise/dashboard" element={<EnterprisePortalPage/>}/><Route path="/reset-password" element={<ResetPasswordPage/>}/><Route element={<CandidateShell/>}><Route path="/" element={<Navigate to="/apply" replace/>}/><Route path="/candidate.html" element={<IndeedApplyPage/>}/><Route path="/apply" element={<IndeedApplyPage/>}/><Route path="/apply/:jobId" element={<IndeedApplyPage/>}/><Route path="/history" element={<HistoryPage/>}/><Route path="/candidate/history" element={<HistoryPage/>}/><Route path="/candidate/reply" element={<ReplyPage/>}/></Route></Routes></EnterpriseErrorBoundary></BrowserRouter></QueryClientProvider></React.StrictMode>);
