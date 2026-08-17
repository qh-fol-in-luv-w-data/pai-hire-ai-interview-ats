export type InterviewStep = 'checking'|'setup'|'consent'|'preparing'|'interviewing'|'submitting'|'survey'|'blocked';
export type InterviewState = { step: InterviewStep; questionIndex: number; error?: string; online: boolean };
export type InterviewAction =
  | {type:'SLOT_OK'; manual?:boolean}|{type:'BLOCK';message:string}|{type:'CONSENT'}|{type:'PREPARE'}
  | {type:'READY'}|{type:'QUESTION';index:number}|{type:'SUBMIT'}|{type:'DONE'}|{type:'ONLINE';online:boolean};
export const initialInterviewState:InterviewState={step:'checking',questionIndex:0,online:navigator.onLine};
export function interviewReducer(state:InterviewState,action:InterviewAction):InterviewState {
  switch(action.type){
    case 'SLOT_OK': return {...state,step:action.manual?'setup':'consent',error:undefined};
    case 'BLOCK': return {...state,step:'blocked',error:action.message};
    case 'CONSENT': return {...state,step:'consent'};
    case 'PREPARE': return {...state,step:'preparing',error:undefined};
    case 'READY': return {...state,step:'interviewing',error:undefined};
    case 'QUESTION': return {...state,questionIndex:action.index};
    case 'SUBMIT': return {...state,step:'submitting'};
    case 'DONE': return {...state,step:'survey'};
    case 'ONLINE': return {...state,online:action.online};
  }
}
