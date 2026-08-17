import { beforeEach, describe, expect, it } from 'vitest';
import { authStore } from './storage';
describe('lưu phiên ứng viên',()=>{
  beforeEach(()=>localStorage.clear());
  it('giữ nguyên các khóa localStorage cũ',()=>{authStore.save({name:'Nguyễn An',email:'an@example.com'},'USR-1');expect(localStorage.getItem('pai_candidate_token')).toBe('USR-1');expect(authStore.user()?.name).toBe('Nguyễn An')});
  it('xóa dữ liệu phiên khi đăng xuất',()=>{authStore.save({name:'An'},'USR-1','ADMIN');authStore.clear();expect(authStore.token()).toBe('');expect(localStorage.getItem('pai_admin_key')).toBeNull()});
});
