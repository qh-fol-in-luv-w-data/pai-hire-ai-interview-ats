import {composeJd,parseJd} from './jd';

it('đọc JD cũ thành các trường dễ sửa',()=>{const value=parseJd('## Tổng quan\nĐội dữ liệu\n## Trách nhiệm\n- Xây pipeline\n## Yêu cầu\n- Biết SQL');expect(value.overview).toBe('Đội dữ liệu');expect(value.responsibilities).toBe('Xây pipeline');expect(value.requirements).toBe('Biết SQL')});
it('tự ghép định dạng khi lưu',()=>{const value=composeJd({overview:'Vai trò mới',responsibilities:'Việc một\nViệc hai',requirements:'Kinh nghiệm',benefits:'Bảo hiểm',other:''});expect(value).toContain('## Trách nhiệm công việc\n- Việc một\n- Việc hai')});
