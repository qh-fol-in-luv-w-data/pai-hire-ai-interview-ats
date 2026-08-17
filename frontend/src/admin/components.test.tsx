import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Application } from '../shared/types';
import { QuestionEditor, ResponsiveApplications } from './AdminApp';
const app:Application={id:'APP-1',job_id:'DEV',name:'Nguyễn An',email:'an@example.com',status:'pending_hr_approval_passed',applied_at:'2026-08-10T00:00:00',interview_prep:{prep_id:'PREP-1',questions:[{n:'01',label:'Giới thiệu',text:'Hãy giới thiệu về bạn.'}]}};
describe('thành phần quản trị',()=>{
  it('bảng responsive mở đúng hồ sơ',()=>{const select=vi.fn();render(<ResponsiveApplications rows={[app]} onSelect={select}/>);fireEvent.click(screen.getByLabelText('Mở hồ sơ'));expect(select).toHaveBeenCalledWith('APP-1')});
  it('đánh dấu đúng câu hỏi đã sửa',()=>{const client=new QueryClient();render(<QueryClientProvider client={client}><QuestionEditor app={app} refresh={()=>undefined}/></QueryClientProvider>);fireEvent.click(screen.getByText('Sửa câu hỏi'));fireEvent.change(screen.getByRole('textbox'),{target:{value:'Hãy giới thiệu kinh nghiệm nổi bật.'}});expect(screen.getByText('Đã thay đổi')).toBeVisible();expect(screen.getByText('1 câu đã thay đổi')).toBeVisible()});
});
