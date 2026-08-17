import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';
afterEach(()=>vi.restoreAllMocks());
describe('API client',()=>{
  it('đọc phản hồi JSON thành công',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({ok:true}),{status:200,headers:{'content-type':'application/json'}})));await expect(api<{ok:boolean}>('/test')).resolves.toEqual({ok:true})});
  it('chuẩn hóa detail lỗi backend',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Không hợp lệ'}),{status:400,headers:{'content-type':'application/json'}})));await expect(api('/test')).rejects.toMatchObject({message:'Không hợp lệ',status:400})});
});
