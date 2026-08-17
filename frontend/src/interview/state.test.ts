import { describe, expect, it } from 'vitest';
import { initialInterviewState, interviewReducer } from './state';
describe('luồng phỏng vấn',()=>{
  it('đi từ kiểm tra link đến phỏng vấn',()=>{let state=interviewReducer(initialInterviewState,{type:'SLOT_OK'});expect(state.step).toBe('consent');state=interviewReducer(state,{type:'PREPARE'});state=interviewReducer(state,{type:'READY'});expect(state.step).toBe('interviewing')});
  it('chặn phiên khi slot hết hạn',()=>expect(interviewReducer(initialInterviewState,{type:'BLOCK',message:'Khung giờ đã kết thúc'})).toMatchObject({step:'blocked',error:'Khung giờ đã kết thúc'}));
  it('giữ chỉ số câu hỏi khi mất mạng',()=>{const interviewing={...initialInterviewState,step:'interviewing' as const,questionIndex:2};expect(interviewReducer(interviewing,{type:'ONLINE',online:false})).toMatchObject({step:'interviewing',questionIndex:2,online:false})});
});
