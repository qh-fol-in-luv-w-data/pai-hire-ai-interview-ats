import { Mic, RotateCcw, Square, Volume2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../shared/ui';

export function AudioRecorder({value,onChange,disabled}:{value?:Blob;onChange:(blob:Blob)=>void;disabled?:boolean}){
  const recorder=useRef<MediaRecorder>(); const chunks=useRef<Blob[]>([]); const [recording,setRecording]=useState(false); const [seconds,setSeconds]=useState(0); const [error,setError]=useState('');
  useEffect(()=>{if(!recording)return;const timer=window.setInterval(()=>setSeconds(v=>v+1),1000);return()=>clearInterval(timer)},[recording]);
  const start=async()=>{try{setError('');const stream=await navigator.mediaDevices.getUserMedia({audio:true});const preferred=MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':'audio/webm';const media=new MediaRecorder(stream,{mimeType:preferred});chunks.current=[];media.ondataavailable=e=>e.data.size&&chunks.current.push(e.data);media.onstop=()=>{onChange(new Blob(chunks.current,{type:media.mimeType}));stream.getTracks().forEach(track=>track.stop())};recorder.current=media;setSeconds(0);setRecording(true);media.start()}catch(e){setError(e instanceof Error?e.message:'Không truy cập được micro')}};
  const stop=()=>{recorder.current?.stop();setRecording(false)};
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex flex-wrap items-center gap-3">{recording?<Button variant="danger" onClick={stop}><Square className="h-4 w-4 fill-current"/>Dừng ghi · {seconds}s</Button>:<Button onClick={start} disabled={disabled}><Mic className="h-4 w-4"/>{value?'Ghi âm lại':'Bắt đầu trả lời'}</Button>}{value&&<><audio className="h-10 max-w-full flex-1" controls src={URL.createObjectURL(value)}/><span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700"><Volume2 className="h-4 w-4"/>Đã lưu</span></>}</div>{error&&<p className="mt-3 text-sm text-red-700">{error}</p>}</div>;
}
