import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import type { Interview, InterviewAnswer } from '../shared/types';
import { adminApi, jsonInit } from '../shared/api';
import { Badge, Button, Card, Drawer, Empty, ErrorState, Loading } from '../shared/ui';
import { statusLabel, statusTone } from '../shared/status';
import { formatDate, levelName, positionName } from '../shared/utils';
import { CheckCircle2, X } from 'lucide-react';

type Report = { candidate_name?: string; position?: string; avg_score?: number; summary?: Record<string, number>; overall_strengths?: string; overall_weaknesses?: string };
type Alert = { id?: number; alert_type?: string; timestamp?: string; snapshot_id?: string };
type Monitoring = { tab_switches?: number; proctoring_alerts?: Alert[] };
type AlertGroup = 'MULTIPLE_FACES' | 'NO_FACE' | 'LOOKING_AWAY' | 'PHONE_DETECTED' | 'CAMERA_BLOCKED' | 'AUDIO_ANOMALY' | 'OTHER';
type QuestionGroup = { key: string; number: string; attempt: number; answers: InterviewAnswer[]; total: number | null };
const alertMeta: Record<AlertGroup, string> = { MULTIPLE_FACES: 'Nhiều khuôn mặt', NO_FACE: 'Mất khuôn mặt', LOOKING_AWAY: 'Nhìn lệch khung hình', PHONE_DETECTED: 'Phát hiện điện thoại', CAMERA_BLOCKED: 'Camera bị che', AUDIO_ANOMALY: 'Âm thanh bất thường', OTHER: 'Cảnh báo khác' };
const visibleGroups: AlertGroup[] = ['MULTIPLE_FACES', 'NO_FACE', 'LOOKING_AWAY', 'PHONE_DETECTED', 'CAMERA_BLOCKED', 'AUDIO_ANOMALY'];
const levelScores: Record<string, number> = { 'nắm vững': 10, 'am hiểu': 7.5, 'có biết qua': 5, 'không biết': 0 };
function groupAlert(value?: string): AlertGroup { const t=(value||'').toUpperCase(); if(t.includes('MULTI')||t.includes('MANY')||t.includes('2_FACE')||t.includes('SEVERAL')||t.includes('EXTRA'))return 'MULTIPLE_FACES'; if(t.includes('NO_FACE')||t.includes('0_FACE')||t.includes('MISSING')||t.includes('NO_PERSON')||t.includes('ABSENT'))return 'NO_FACE'; if(t.includes('LOOK')||t.includes('AWAY'))return 'LOOKING_AWAY'; if(t.includes('PHONE'))return 'PHONE_DETECTED'; if(t.includes('CAMERA')||t.includes('BLOCK'))return 'CAMERA_BLOCKED'; if(t.includes('AUDIO')||t.includes('SOUND'))return 'AUDIO_ANOMALY'; return 'OTHER'; }
function aiScore(level?: string) { return level ? levelScores[level.toLowerCase()] ?? null : null; }
function scoreLabel(score: number | null | undefined) { return score == null ? 'Chưa chấm' : `${score.toFixed(1)}/10`; }
function groupInterviewAnswers(answers: NonNullable<Interview['answers']>): QuestionGroup[] {
  const groups = new Map<string, QuestionGroup>();
  answers.forEach(answer => {
    const [number] = String(answer.question_number || '').split('.', 1);
    const attempt = answer.attempt_number || 1;
    const key = `${attempt}:${number}`;
    const group = groups.get(key) || { key, number, attempt, answers: [], total: null };
    group.answers.push(answer);
    groups.set(key, group);
  });
  groups.forEach(group => {
    const baseScore=aiScore(group.answers.find(answer=>!answer.question_number.includes('.'))?.ai_level);
    const followUpScores=group.answers.filter(answer=>answer.question_number.includes('.')).map(answer=>aiScore(answer.ai_level)).filter((score): score is number=>score!=null);
    const higherFollowUps=baseScore==null?followUpScores:followUpScores.filter(score=>score>baseScore);
    const includedScores=baseScore==null?followUpScores:[baseScore,...higherFollowUps];
    group.total=includedScores.length?includedScores.reduce((sum,score)=>sum+score,0)/includedScores.length:null;
  });
  return [...groups.values()];
}

export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex items-center gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-2xl animate-in slide-in-from-bottom-5 fade-in duration-300">
      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
      <p>{message}</p>
      <button onClick={onClose} className="ml-2 rounded-full p-1 hover:bg-slate-800 transition">
        <X className="h-4 w-4 text-slate-400 hover:text-white" />
      </button>
    </div>
  );
}

export function InterviewDrawerPro({ id, onClose }: { id?: string; onClose: () => void }) {
  const qc = useQueryClient(); 
  const [showMonitoringDetails, setShowMonitoringDetails] = useState(false); 
  const [exporting, setExporting] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const detail = useQuery({ queryKey: ['interview', id], queryFn: () => adminApi<Interview>(`/interview/${id}`), enabled: !!id });
  const report = useQuery({ queryKey: ['interview-report', id], queryFn: () => adminApi<Report>(`/interview/${id}/report`), enabled: !!id });
  const monitoring = useQuery({ queryKey: ['interview-monitoring', id], queryFn: () => adminApi<Monitoring>(`/admin/proctoring/logs?interview_id=${encodeURIComponent(id || '')}`), enabled: !!id });
  const review = useMutation({ mutationFn: (status: string) => adminApi(`/interview/${id}/review`, jsonInit('PATCH', { status })), onSuccess: () => { qc.invalidateQueries({ queryKey: ['interviews'] }); detail.refetch(); report.refetch(); } });
  const sendResult = useMutation({ mutationFn: () => adminApi(`/interview/${id}/send-result-email`, { method: 'POST' }) });
  const reEvaluate = useMutation({ 
    mutationFn: () => adminApi(`/interview/${id}/evaluate`, { method: 'POST' }), 
    onSuccess: () => { 
      qc.invalidateQueries({ queryKey: ['interviews'] }); 
      detail.refetch(); 
      report.refetch(); 
      setToastMessage('Hệ thống đang chấm điểm lại trong nền, vui lòng chờ vài phút rồi tải lại trang.');
    } 
  });
  const alerts=monitoring.data?.proctoring_alerts||[];
  const counts=alerts.reduce<Record<AlertGroup,number>>((result,alert)=>{const key=groupAlert(alert.alert_type);result[key]=(result[key]||0)+1;return result;},{MULTIPLE_FACES:0,NO_FACE:0,LOOKING_AWAY:0,PHONE_DETECTED:0,CAMERA_BLOCKED:0,AUDIO_ANOMALY:0,OTHER:0});
  const score=report.data?.avg_score??detail.data?.avg_score;
  const position=detail.data?.application_source==='api'?'—':positionName(detail.data?.position_id||'');
  const questionGroups=groupInterviewAnswers(detail.data?.answers||[]);
  const printReport=()=>{
    if(!detail.data||!report.data)return;
    setExporting(true);
    const candidateName=(detail.data.candidate_name||report.data.candidate_name||id||'ung-vien').normalize('NFD').replace(/\p{Diacritic}/gu,'').replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-+|-+$/g,'')||'ung-vien';
    const reportFilename=`bao-cao-phong-van-${candidateName}`;
    const answers=questionGroups.map(group=>`<article>
      <div class="question-heading"><div class="question-number">Câu ${safe(group.number)}${group.attempt > 1 ? ` · Lần phỏng vấn ${group.attempt}` : ''}</div><strong>Điểm nhóm: ${scoreLabel(group.total)}</strong></div>
      <p class="calculation">Cách tính: chỉ follow-up có điểm cao hơn câu gốc mới được tính trung bình cùng câu gốc.</p>
      ${group.answers.map(answer=>`<section class="answer-item"><div class="answer-item-heading"><span>${answer.question_number.includes('.') ? `Câu hỏi đào sâu ${answer.question_number.split('.')[1]}` : 'Câu hỏi gốc'}</span><b>${scoreLabel(aiScore(answer.ai_level))} · ${safe(answer.ai_level||'Chưa đánh giá')}</b></div><h3>${safe(answer.question_text||'Nội dung câu hỏi')}</h3><section class="answer"><span>Câu trả lời</span><p>${safe(answer.transcript||'Không có bản ghi nội dung.').replace(/\n/g,'<br>')}</p></section>${answer.ai_feedback?`<p class="feedback"><b>Nhận xét AI:</b> ${safe(answer.ai_feedback)}</p>`:''}</section>`).join('')}
    </article>`).join('');
    const strengths=report.data.overall_strengths?`<section class="insight"><h3>Điểm mạnh</h3><p>${safe(report.data.overall_strengths)}</p></section>`:'';
    const weaknesses=report.data.overall_weaknesses?`<section class="insight"><h3>Điểm cần cải thiện</h3><p>${safe(report.data.overall_weaknesses)}</p></section>`:'';
    const html=`<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>${reportFilename}</title><style>
      @page{size:A4;margin:14mm}*{box-sizing:border-box}body{margin:0;color:#172033;font:10.5pt Arial,sans-serif;line-height:1.5}.head{padding:18mm 16mm;background:#0b2447;color:#fff;border-radius:5mm}.eyebrow{font-size:8pt;letter-spacing:1.6px;text-transform:uppercase;color:#b9d7ff;font-weight:bold}.head h1{margin:7px 0 2px;font-size:24pt;line-height:1.2}.head p{margin:0;color:#d7e5f5}.body{padding:9mm 1mm 0}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:3mm;margin-bottom:7mm}.metric{min-height:22mm;padding:4mm;border:1px solid #d9e2ee;border-radius:3mm;background:#f8fafc}.metric small{display:block;color:#64748b;font-size:8pt}.metric strong{display:block;margin-top:5px;font-size:14pt;line-height:1.2;color:#102a4c}.section-title{margin:8mm 0 3mm;font-size:15pt;color:#102a4c}.insights{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-bottom:7mm}.insight{padding:4mm;border-left:3px solid #2563eb;background:#eff6ff}.insight h3{margin:0 0 3px;font-size:10pt;color:#1d4f91}.insight p{margin:0;white-space:pre-line}article{break-inside:avoid;page-break-inside:avoid;border-top:1px solid #d9e2ee;padding:6mm 0}.question-heading{display:flex;align-items:center;justify-content:space-between;gap:4mm}.question-heading strong{color:#0f5cc0;font-size:10pt}.question-number{color:#2563eb;font-size:8pt;font-weight:bold;letter-spacing:1px;text-transform:uppercase}.calculation{margin:2mm 0 4mm;color:#64748b;font-size:8.5pt}.answer-item{border-top:1px dashed #d9e2ee;padding:4mm 0}.answer-item-heading{display:flex;justify-content:space-between;gap:4mm;color:#52657b;font-size:8.5pt}.answer-item-heading b{color:#0f5cc0}.answer-item h3{margin:2mm 0 3mm;font-size:11pt;line-height:1.45}.answer{padding:4mm;border-radius:3mm;background:#f4f7fb}.answer span{font-size:8pt;font-weight:bold;color:#52657b;text-transform:uppercase;letter-spacing:.5px}.answer p{margin:3px 0 0;white-space:normal}.feedback{margin:3mm 0 0;color:#405168}.footer{margin-top:8mm;padding-top:3mm;border-top:1px solid #d9e2ee;color:#64748b;font-size:8pt;text-align:center}@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.head{break-inside:avoid}.footer{position:fixed;bottom:0;left:0;right:0}.summary{break-inside:avoid}}
    </style></head><body><header class="head"><div class="eyebrow">PAI Hire · Báo cáo phỏng vấn</div><h1>${safe(report.data.candidate_name||detail.data.candidate_name||'Ứng viên')}</h1><p>${safe(position)} · ${safe(levelName(detail.data.level))} · ${formatDate(detail.data.submitted_at)}</p></header><main class="body"><section class="summary"><div class="metric"><small>Điểm AI tổng</small><strong>${scoreLabel(score)}</strong></div><div class="metric"><small>Trạng thái</small><strong>${safe(statusLabel(detail.data.status))}</strong></div><div class="metric"><small>Số câu trả lời</small><strong>${detail.data.answers?.length||0}</strong></div><div class="metric"><small>Chuyển tab</small><strong>${monitoring.data?.tab_switches??detail.data.tab_switches??0}</strong></div></section>${strengths||weaknesses?`<section class="insights">${strengths}${weaknesses}</section>`:''}<h2 class="section-title">Nội dung phỏng vấn</h2>${answers||'<p>Chưa có câu trả lời.</p>'}</main><footer class="footer">PAI Hire · Báo cáo được tạo ngày ${formatDate(new Date().toISOString())}</footer></body></html>`;
    const reportWindow=window.open('', '_blank');
    if(!reportWindow){setExporting(false);alert('Trình duyệt đang chặn cửa sổ xuất báo cáo. Hãy cho phép pop-up rồi thử lại.');return;}
    reportWindow.document.open();
    reportWindow.document.write(html);
    reportWindow.document.close();
    window.setTimeout(()=>{reportWindow.focus();reportWindow.print();setExporting(false);},250);
  };
  const exportPdf=async()=>{
    if(!id||!detail.data)return;
    setExporting(true);
    try{
      const adminKey=localStorage.getItem('pai_admin_key')||sessionStorage.getItem('pai_admin_key')||'';
      const response=await fetch(`/interview/${encodeURIComponent(id)}/report.pdf`,{credentials:'same-origin',headers:{'X-Admin-Key':adminKey}});
      if(!response.ok){
        const payload=await response.json().catch(()=>null) as {detail?:string}|null;
        throw new Error(payload?.detail||'Không thể tạo báo cáo PDF.');
      }
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      const candidate=(detail.data.candidate_name||id).normalize('NFD').replace(/\p{Diacritic}/gu,'').replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-+|-+$/g,'')||'ung-vien';
      link.href=url;link.download=`bao-cao-phong-van-${candidate}.pdf`;
      document.body.appendChild(link);link.click();link.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){
      alert(error instanceof Error?error.message:'Không thể xuất báo cáo PDF.');
    }finally{setExporting(false);}
  };
  const finalStatus=detail.data?.status;
  
  return (
    <>
      <Drawer open={!!id} onClose={onClose} title={detail.data?.candidate_name||'Chi tiết phỏng vấn'} footer={detail.data&&<div className="space-y-3"><div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" onClick={()=>reEvaluate.mutate()} disabled={reEvaluate.isPending}>{reEvaluate.isPending?'Đang xử lý...':'Chấm điểm lại'}</Button><Button variant="secondary" onClick={exportPdf} disabled={!report.data||exporting}>{exporting?'Đang tạo PDF...':'Xuất báo cáo'}</Button>{finalStatus==='failed'&&<Button variant="danger" onClick={()=>sendResult.mutate()} disabled={sendResult.isPending}>{sendResult.isPending?'Đang gửi...':'Gửi mail từ chối'}</Button>}{finalStatus==='passed'&&<Button onClick={()=>sendResult.mutate()} disabled={sendResult.isPending}>{sendResult.isPending?'Đang gửi...':'Gửi mail đạt phỏng vấn'}</Button>}{finalStatus!=='passed'&&finalStatus!=='failed'&&<><Button variant="danger" onClick={()=>review.mutate('failed')}>Đánh dấu không đạt</Button><Button onClick={()=>review.mutate('passed')}>Đánh dấu đạt</Button></>}</div>{sendResult.isSuccess&&<p className="text-right text-sm font-semibold text-emerald-700">Đã gửi email kết quả cho ứng viên.</p>}{sendResult.error&&<p className="text-right text-sm font-semibold text-red-700">{sendResult.error.message}</p>}</div>}>
        {detail.isLoading?<Loading/>:detail.error?<ErrorState message={detail.error.message}/>:detail.data?<div data-interview-report className="space-y-4"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="muted">{position} · {levelName(detail.data.level)}</p><div className="mt-1 flex items-center gap-4"><p className="text-2xl font-extrabold">{scoreLabel(score)}</p><Button variant="secondary" onClick={()=>reEvaluate.mutate()} disabled={reEvaluate.isPending}>{reEvaluate.isPending?'Đang xử lý...':'Chấm điểm lại'}</Button></div><p className="mt-1 text-xs text-slate-500">Điểm AI tổng theo thang 10 · Nộp bài: {formatDate(detail.data.submitted_at)} · {detail.data.answers?.length||0} câu trả lời</p></div><Badge tone={statusTone(detail.data.status)}>{statusLabel(detail.data.status)}</Badge></div><div className="mt-4 grid gap-3 sm:grid-cols-4"><div className="rounded-xl bg-blue-50 p-3"><p className="text-xs text-blue-700">Điểm AI tổng</p><p className="font-bold text-blue-950">{scoreLabel(score)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Điểm HR</p><p className="font-bold">{scoreLabel(detail.data.hr_score)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Điểm chuyên gia</p><p className="font-bold">{scoreLabel(detail.data.expert_score)}</p></div><div className="rounded-xl bg-amber-50 p-3"><p className="text-xs text-amber-700">Chuyển tab</p><p className="font-bold text-amber-800">{monitoring.data?.tab_switches??detail.data.tab_switches??0} lần</p></div></div></Card><Card className="p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-extrabold">Giám sát phỏng vấn</h3><p className="mt-1 text-xs text-slate-500">Chỉ hiện tổng số lần; log thô được ẩn mặc định.</p></div><button type="button" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-brand-700 hover:bg-blue-50" onClick={()=>setShowMonitoringDetails(value=>!value)}>{showMonitoringDetails?'Ẩn chi tiết ↑':'Xem chi tiết ↓'}</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{visibleGroups.map(group=><div key={group} className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-bold text-amber-900">{alertMeta[group]}</p><p className="mt-2 text-2xl font-extrabold text-amber-900">{counts[group]} <span className="text-xs font-bold">lần</span></p></div>)}</div>{showMonitoringDetails&&<div className="mt-4 border-t border-slate-100 pt-4">{alerts.length?<div className="space-y-2">{alerts.map((alert,index)=><div key={alert.id||index} className="flex flex-wrap justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600"><span className="font-bold">{alertMeta[groupAlert(alert.alert_type)]}</span><span>{formatDate(alert.timestamp)}</span></div>)}</div>:<p className="text-sm text-emerald-700">Không có log vi phạm.</p>}</div>}</Card><Card className="p-5"><h3 className="font-extrabold">Tổng hợp đánh giá</h3><div className="mt-3 grid gap-3 sm:grid-cols-3">{Object.entries(report.data?.summary||{}).map(([key,value])=><div key={key} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{key}</p><p className="font-bold">{value} câu</p></div>)}</div>{report.data?.overall_strengths&&<p className="mt-4 text-sm"><strong>Điểm mạnh:</strong> {report.data.overall_strengths}</p>}{report.data?.overall_weaknesses&&<p className="mt-2 text-sm"><strong>Điểm yếu:</strong> {report.data.overall_weaknesses}</p>}</Card>{questionGroups.length?<><Card className="border-blue-100 bg-blue-50/50 p-4"><p className="text-sm font-bold text-blue-950">Cách tính điểm AI</p><p className="mt-1 text-xs leading-5 text-blue-800">Nắm vững: 10/10 · Am hiểu: 7.5/10 · Có biết qua: 5/10 · Không biết: 0/10. Follow-up chỉ được cộng vào trung bình khi điểm cao hơn câu gốc; follow-up thấp hơn hoặc bằng câu gốc không làm giảm điểm nhóm. Điểm AI tổng là trung bình các điểm nhóm.</p></Card>{questionGroups.map(group=><QuestionScoreCard key={group.key} group={group}/>)}</>:<Empty title="Chưa có câu trả lời"/>}</div>:null}
      </Drawer>
      {toastMessage && <Toast message={toastMessage} onClose={() => setToastMessage(null)} />}
    </>
  );
}

function QuestionScoreCard({ group }: { group: QuestionGroup }) {
  return <Card className="overflow-hidden p-0">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-blue-100 bg-blue-50 px-5 py-4">
      <div>
        <p className="text-xs font-extrabold tracking-wide text-brand-700">CÂU {group.number}{group.attempt > 1 ? ` · LẦN PHỎNG VẤN ${group.attempt}` : ''}</p>
        <p className="mt-1 text-xs text-slate-600">Chỉ follow-up cao hơn câu gốc mới được tính vào điểm nhóm.</p>
      </div>
      <div className="rounded-xl bg-white px-3 py-2 text-right shadow-sm ring-1 ring-blue-100"><p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Điểm nhóm</p><p className="text-lg font-extrabold text-brand-700">{scoreLabel(group.total)}</p></div>
    </div>
    <div className="divide-y divide-slate-100">{group.answers.map((answer,index)=>{
      const isFollowUp=answer.question_number.includes('.');
      return <div className="p-5" key={`${answer.question_number}-${index}`}>
        <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs font-extrabold text-slate-600">{isFollowUp?`FOLLOW-UP ${answer.question_number.split('.')[1]}`:'CÂU HỎI GỐC'}</p><div className="flex flex-wrap gap-2 text-xs"><Badge tone="info">Mức độ: {answer.ai_level||'Chưa đánh giá'}</Badge><Badge tone={aiScore(answer.ai_level)==null?'neutral':'success'}>Điểm AI: {scoreLabel(aiScore(answer.ai_level))}</Badge></div></div>
        <h3 className="mt-2 font-bold leading-6">{answer.question_text||'Nội dung câu hỏi'}</h3>
        <div className="mt-3 rounded-xl bg-slate-50 p-4 text-sm leading-6">{answer.transcript||'Không có bản ghi nội dung.'}</div>
        {answer.ai_feedback&&<p className="mt-3 text-sm text-slate-600"><strong>Nhận xét AI:</strong> {answer.ai_feedback}</p>}
      </div>;
    })}</div>
  </Card>;
}

function safe(value:string){return value.replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]||char));}
