import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import type { Interview } from '../shared/types';
import { adminApi, jsonInit } from '../shared/api';
import { Badge, Button, Card, Drawer, Empty, ErrorState, Loading } from '../shared/ui';
import { statusLabel, statusTone } from '../shared/status';
import { formatDate, levelName, positionName } from '../shared/utils';
import { CheckCircle2, X } from 'lucide-react';

type Report = { candidate_name?: string; position?: string; avg_score?: number; summary?: Record<string, number>; overall_strengths?: string; overall_weaknesses?: string };
type Alert = { id?: number; alert_type?: string; timestamp?: string; snapshot_id?: string };
type Monitoring = { tab_switches?: number; proctoring_alerts?: Alert[] };
type AlertGroup = 'MULTIPLE_FACES' | 'NO_FACE' | 'LOOKING_AWAY' | 'PHONE_DETECTED' | 'CAMERA_BLOCKED' | 'AUDIO_ANOMALY' | 'OTHER';
const alertMeta: Record<AlertGroup, string> = { MULTIPLE_FACES: 'Nhiều khuôn mặt', NO_FACE: 'Mất khuôn mặt', LOOKING_AWAY: 'Nhìn lệch khung hình', PHONE_DETECTED: 'Phát hiện điện thoại', CAMERA_BLOCKED: 'Camera bị che', AUDIO_ANOMALY: 'Âm thanh bất thường', OTHER: 'Cảnh báo khác' };
const visibleGroups: AlertGroup[] = ['MULTIPLE_FACES', 'NO_FACE', 'LOOKING_AWAY', 'PHONE_DETECTED', 'CAMERA_BLOCKED', 'AUDIO_ANOMALY'];
function groupAlert(value?: string): AlertGroup { const t=(value||'').toUpperCase(); if(t.includes('MULTI')||t.includes('MANY')||t.includes('2_FACE')||t.includes('SEVERAL')||t.includes('EXTRA'))return 'MULTIPLE_FACES'; if(t.includes('NO_FACE')||t.includes('0_FACE')||t.includes('MISSING')||t.includes('NO_PERSON')||t.includes('ABSENT'))return 'NO_FACE'; if(t.includes('LOOK')||t.includes('AWAY'))return 'LOOKING_AWAY'; if(t.includes('PHONE'))return 'PHONE_DETECTED'; if(t.includes('CAMERA')||t.includes('BLOCK'))return 'CAMERA_BLOCKED'; if(t.includes('AUDIO')||t.includes('SOUND'))return 'AUDIO_ANOMALY'; return 'OTHER'; }

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
  const download=()=>{if(!detail.data||!report.data)return;const answers=(detail.data.answers||[]).map((a,i)=>`<article><h3>Câu ${safe(String(a.question_number||i+1))}</h3><p><b>${safe(a.question_text||'Nội dung câu hỏi')}</b></p><p class="answer">${safe(a.transcript||'Không có bản ghi nội dung.')}</p><p class="meta">Mức AI: ${safe(a.ai_level||'Chưa đánh giá')} · Điểm: ${a.score??'—'}/10</p><p>${safe(a.ai_feedback||'')}</p></article>`).join('');const html=`<!doctype html><html lang="vi"><meta charset="utf-8"><title>Báo cáo phỏng vấn</title><style>*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#172033;font:14px Arial,sans-serif}.page{max-width:920px;margin:32px auto;background:#fff;border:1px solid #e1e8f0;border-radius:22px;overflow:hidden;box-shadow:0 18px 50px #10233a18}.head{padding:34px 40px;background:linear-gradient(135deg,#071426,#123765);color:#fff}.eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#9cc5ff;font-weight:bold}.head h1{margin:10px 0 4px;font-size:30px}.head p{margin:0;color:#cbd8e8}.body{padding:28px 40px}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:28px}.metric{padding:15px;border:1px solid #e1e8f0;border-radius:14px;background:#f8fafc}.metric small{display:block;color:#64748b;font-size:11px}.metric strong{display:block;margin-top:7px;font-size:21px;color:#071426}article{border-top:1px solid #e1e8f0;padding:20px 0}article h3{margin:0 0 9px;color:#1769d1;font-size:13px;text-transform:uppercase;letter-spacing:1px}article p{line-height:1.7;margin:7px 0}.answer{padding:14px;border-radius:12px;background:#f5f8fc;color:#334155}.meta{color:#64748b;font-size:12px}@media print{body{background:#fff}.page{margin:0;border:0;border-radius:0;box-shadow:none}}</style><div class="page"><header class="head"><div class="eyebrow">PAI Hire · Báo cáo phỏng vấn</div><h1>${safe(report.data.candidate_name||detail.data.candidate_name||'Ứng viên')}</h1><p>${safe(position)} · ${formatDate(detail.data.submitted_at)}</p></header><main class="body"><div class="summary"><div class="metric"><small>Điểm HR</small><strong>${detail.data.hr_score??score??'—'}/10</strong></div><div class="metric"><small>Trạng thái</small><strong>${safe(statusLabel(detail.data.status))}</strong></div><div class="metric"><small>Số câu trả lời</small><strong>${detail.data.answers?.length||0}</strong></div><div class="metric"><small>Chuyển tab</small><strong>${monitoring.data?.tab_switches??detail.data.tab_switches??0}</strong></div></div><h2>Nội dung câu trả lời</h2>${answers}</main></div><script>window.onload=()=>window.print()<\/script></html>`;const reportWindow=window.open('','_blank','noopener,noreferrer');if(!reportWindow){alert('Trình duyệt đang chặn cửa sổ xuất PDF. Hãy cho phép pop-up rồi thử lại.');return;}reportWindow.document.open();reportWindow.document.write(html);reportWindow.document.close();};
  const exportPdf=async()=>{const node=document.querySelector<HTMLElement>('[data-interview-report]');if(!node||!detail.data)return;setExporting(true);try{const [{default:html2canvas},{jsPDF}]=await Promise.all([import('html2canvas'),import('jspdf')]);const canvas=await html2canvas(node,{scale:2,backgroundColor:'#ffffff',useCORS:true,windowWidth:node.scrollWidth});const pdf=new jsPDF({orientation:'p',unit:'mm',format:'a4'});const width=210;const height=297;const imageHeight=canvas.height*width/canvas.width;let offset=0;while(offset<imageHeight){pdf.addImage(canvas.toDataURL('image/png'),'PNG',0,-offset,width,imageHeight,undefined,'FAST');offset+=height;if(offset<imageHeight)pdf.addPage();}pdf.save(`bao-cao-phong-van-${(detail.data.candidate_name||id||'ung-vien').replace(/[^a-zA-Z0-9_-]+/g,'-')}.pdf`);}finally{setExporting(false);}};
  const finalStatus=detail.data?.status;
  
  return (
    <>
      <Drawer open={!!id} onClose={onClose} title={detail.data?.candidate_name||'Chi tiết phỏng vấn'} footer={detail.data&&<div className="space-y-3"><div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" onClick={()=>reEvaluate.mutate()} disabled={reEvaluate.isPending}>{reEvaluate.isPending?'Đang xử lý...':'Chấm điểm lại'}</Button><Button variant="secondary" onClick={exportPdf} disabled={!report.data||exporting}>{exporting?'Đang tạo PDF...':'Xuất báo cáo'}</Button>{finalStatus==='failed'&&<Button variant="danger" onClick={()=>sendResult.mutate()} disabled={sendResult.isPending}>{sendResult.isPending?'Đang gửi...':'Gửi mail từ chối'}</Button>}{finalStatus==='passed'&&<Button onClick={()=>sendResult.mutate()} disabled={sendResult.isPending}>{sendResult.isPending?'Đang gửi...':'Gửi mail đạt phỏng vấn'}</Button>}{finalStatus!=='passed'&&finalStatus!=='failed'&&<><Button variant="danger" onClick={()=>review.mutate('failed')}>Đánh dấu không đạt</Button><Button onClick={()=>review.mutate('passed')}>Đánh dấu đạt</Button></>}</div>{sendResult.isSuccess&&<p className="text-right text-sm font-semibold text-emerald-700">Đã gửi email kết quả cho ứng viên.</p>}{sendResult.error&&<p className="text-right text-sm font-semibold text-red-700">{sendResult.error.message}</p>}</div>}>
        {detail.isLoading?<Loading/>:detail.error?<ErrorState message={detail.error.message}/>:detail.data?<div data-interview-report className="space-y-4"><Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="muted">{position} · {levelName(detail.data.level)}</p><div className="mt-1 flex items-center gap-4"><p className="text-2xl font-extrabold">{score==null?'Chưa có điểm':`${score}/10`}</p><Button variant="secondary" onClick={()=>reEvaluate.mutate()} disabled={reEvaluate.isPending}>{reEvaluate.isPending?'Đang xử lý...':'Chấm điểm lại'}</Button></div><p className="mt-1 text-xs text-slate-500">Nộp bài: {formatDate(detail.data.submitted_at)} · {detail.data.answers?.length||0} câu trả lời</p></div><Badge tone={statusTone(detail.data.status)}>{statusLabel(detail.data.status)}</Badge></div><div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Điểm HR</p><p className="font-bold">{detail.data.hr_score??(score==null?'Chưa chấm':`${score}/10`)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">Điểm chuyên gia</p><p className="font-bold">{detail.data.expert_score??'Chưa chấm'}</p></div><div className="rounded-xl bg-amber-50 p-3"><p className="text-xs text-amber-700">Chuyển tab</p><p className="font-bold text-amber-800">{monitoring.data?.tab_switches??detail.data.tab_switches??0} lần</p></div></div></Card><Card className="p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-extrabold">Giám sát phỏng vấn</h3><p className="mt-1 text-xs text-slate-500">Chỉ hiện tổng số lần; log thô được ẩn mặc định.</p></div><button type="button" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-brand-700 hover:bg-blue-50" onClick={()=>setShowMonitoringDetails(value=>!value)}>{showMonitoringDetails?'Ẩn chi tiết ↑':'Xem chi tiết ↓'}</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{visibleGroups.map(group=><div key={group} className="rounded-2xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-bold text-amber-900">{alertMeta[group]}</p><p className="mt-2 text-2xl font-extrabold text-amber-900">{counts[group]} <span className="text-xs font-bold">lần</span></p></div>)}</div>{showMonitoringDetails&&<div className="mt-4 border-t border-slate-100 pt-4">{alerts.length?<div className="space-y-2">{alerts.map((alert,index)=><div key={alert.id||index} className="flex flex-wrap justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600"><span className="font-bold">{alertMeta[groupAlert(alert.alert_type)]}</span><span>{formatDate(alert.timestamp)}</span></div>)}</div>:<p className="text-sm text-emerald-700">Không có log vi phạm.</p>}</div>}</Card><Card className="p-5"><h3 className="font-extrabold">Tổng hợp đánh giá</h3><div className="mt-3 grid gap-3 sm:grid-cols-3">{Object.entries(report.data?.summary||{}).map(([key,value])=><div key={key} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{key}</p><p className="font-bold">{value} câu</p></div>)}</div>{report.data?.overall_strengths&&<p className="mt-4 text-sm"><strong>Điểm mạnh:</strong> {report.data.overall_strengths}</p>}{report.data?.overall_weaknesses&&<p className="mt-2 text-sm"><strong>Điểm yếu:</strong> {report.data.overall_weaknesses}</p>}</Card>{detail.data.answers?.length?detail.data.answers.map((a,i)=><Card className="p-5" key={`${a.question_number}-${i}`}><p className="text-xs font-extrabold text-brand-700">CÂU {a.question_number}</p><h3 className="mt-2 font-bold leading-6">{a.question_text||'Nội dung câu hỏi'}</h3><div className="mt-3 rounded-xl bg-slate-50 p-4 text-sm leading-6">{a.transcript||'Không có bản ghi nội dung.'}</div><div className="mt-3 flex flex-wrap gap-2 text-xs"><Badge tone="info">Mức độ: {a.ai_level||'Chưa đánh giá'}</Badge><Badge tone="neutral">Điểm: {a.score??'—'}/10</Badge></div>{a.ai_feedback&&<p className="mt-3 text-sm text-slate-600"><strong>Nhận xét AI:</strong> {a.ai_feedback}</p>}</Card>):<Empty title="Chưa có câu trả lời"/>}</div>:null}
      </Drawer>
      {toastMessage && <Toast message={toastMessage} onClose={() => setToastMessage(null)} />}
    </>
  );
}
function safe(value:string){return value.replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]||char));}
