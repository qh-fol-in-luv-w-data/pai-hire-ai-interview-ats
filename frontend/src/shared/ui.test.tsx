import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Dialog, Drawer, SelectField } from './ui';
describe('dialog và drawer dùng chung',()=>{
  it('xác nhận hành động trong dialog',()=>{const confirm=vi.fn();render(<Dialog open title="Gửi thư mời?" onClose={()=>undefined} onConfirm={confirm}/>);fireEvent.click(screen.getByText('Xác nhận'));expect(confirm).toHaveBeenCalledOnce()});
  it('đóng drawer từ nút có nhãn truy cập',()=>{const close=vi.fn();render(<Drawer open title="Hồ sơ ứng viên" onClose={close}>Nội dung</Drawer>);fireEvent.click(screen.getByLabelText('Đóng'));expect(close).toHaveBeenCalledOnce()});
  it('chọn giá trị trong dropdown mới',()=>{const change=vi.fn();render(<SelectField value="" onChange={change} options={[{value:'',label:'Tất cả lĩnh vực'},{value:'tech',label:'Công nghệ'}]}/>);fireEvent.click(screen.getByRole('button',{name:'Tất cả lĩnh vực'}));fireEvent.click(screen.getByRole('option',{name:'Công nghệ'}));expect(change).toHaveBeenCalledWith('tech')});
});
