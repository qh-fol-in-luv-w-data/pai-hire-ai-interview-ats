import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AudioRecorder } from './AudioRecorder';
describe('trình ghi âm',()=>{
  it('hiển thị trạng thái bắt đầu khi chưa có bản ghi',()=>{render(<AudioRecorder onChange={vi.fn()}/>);expect(screen.getByText('Bắt đầu trả lời')).toBeEnabled()});
  it('cho phép ghi lại khi đã có bản ghi',()=>{render(<AudioRecorder value={new Blob(['audio'],{type:'audio/webm'})} onChange={vi.fn()}/>);expect(screen.getByText('Ghi âm lại')).toBeVisible();expect(screen.getByText('Đã lưu')).toBeVisible()});
});
