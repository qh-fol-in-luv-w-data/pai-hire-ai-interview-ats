import { describe, expect, it } from 'vitest';
import { statusLabel, statusTone } from './status';
import { positionName, uniquePositions } from './utils';
describe('ánh xạ trạng thái',()=>{
  it('hiển thị trạng thái đã gửi link phỏng vấn bằng tiếng Việt',()=>expect(statusLabel('interview_link_sent')).toBe('Đã gửi link phỏng vấn'));
  it('phân loại trạng thái chờ duyệt là cảnh báo',()=>expect(statusTone('pending_hr_approval_passed')).toBe('warning'));
  it('giữ trạng thái chưa biết để không làm mất thông tin',()=>expect(statusLabel('custom_state')).toBe('custom_state'));
});
describe('tên vị trí tuyển dụng',()=>{
  it('Việt hóa tên tiếng Anh và bỏ cấp bậc khỏi tên hiển thị',()=>expect(positionName('Junior_Data_Analyst')).toBe('Chuyên viên phân tích dữ liệu'));
  it('gộp các cấp bậc thành một vị trí',()=>expect(uniquePositions([{id:'Entry_Data_Analyst'},{id:'Junior_Data_Analyst'},{id:'Senior_Data_Analyst'}])).toEqual([{id:'Junior_Data_Analyst'}]));
});
