export function formatDate(value?: string, dateOnly = false) { if (!value) return '—'; const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`); if (Number.isNaN(d.getTime())) return value; return new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'short', ...(dateOnly ? {} : { timeStyle: 'short' }) }).format(d); }
const positionTranslations:Record<string,string>={
  '3d artist':'Họa sĩ 3D','aiml engineer':'Kỹ sư AI/ML','ai ml engineer':'Kỹ sư AI/ML',
  'account executive (agency)':'Chuyên viên quản lý khách hàng','account executive agency':'Chuyên viên quản lý khách hàng','account executive':'Chuyên viên quản lý khách hàng',
  'automation tester':'Chuyên viên kiểm thử tự động','b2b sales executive':'Chuyên viên kinh doanh doanh nghiệp',
  'backend developer':'Lập trình viên Backend','brand executive':'Chuyên viên thương hiệu','business analyst':'Chuyên viên phân tích nghiệp vụ',
  'content creator':'Chuyên viên sáng tạo nội dung','cyber security analyst':'Chuyên viên phân tích an ninh mạng',
  'data analyst':'Chuyên viên phân tích dữ liệu','data engineer':'Kỹ sư dữ liệu','devops engineer':'Kỹ sư DevOps',
  'digital marketer':'Chuyên viên tiếp thị số','digital marketing executive':'Chuyên viên tiếp thị số',
  'e-commerce executive':'Chuyên viên thương mại điện tử','e commerce executive':'Chuyên viên thương mại điện tử','event coordinator':'Điều phối viên sự kiện',
  'financial analyst':'Chuyên viên phân tích tài chính','frontend developer':'Lập trình viên Frontend',
  'fullstack developer':'Lập trình viên Fullstack','general accountant':'Kế toán tổng hợp','graphic designer':'Chuyên viên thiết kế đồ họa',
  'hr admin':'Chuyên viên hành chính nhân sự','importexport executive':'Chuyên viên xuất nhập khẩu','import export executive':'Chuyên viên xuất nhập khẩu',
  'internal auditor':'Kiểm toán viên nội bộ','l&d executive':'Chuyên viên đào tạo và phát triển','logistics coordinator':'Điều phối viên vận tải',
  'maintenance engineer':'Kỹ sư bảo trì','mechanical engineer':'Kỹ sư cơ khí','mobile developer (iosandroid)':'Lập trình viên ứng dụng di động',
  'mobile developer iosandroid':'Lập trình viên ứng dụng di động','mobile developer':'Lập trình viên ứng dụng di động','motion graphic designer':'Chuyên viên thiết kế đồ họa chuyển động',
  'office admin':'Chuyên viên hành chính văn phòng','pr executive':'Chuyên viên quan hệ công chúng',
  'payable accountant':'Kế toán công nợ phải trả','procurement executive':'Chuyên viên thu mua','procurement specialist':'Chuyên viên thu mua',
  'qaqc tester':'Chuyên viên kiểm thử chất lượng','qa qc tester':'Chuyên viên kiểm thử chất lượng','qc engineer':'Kỹ sư quản lý chất lượng','receivable accountant':'Kế toán công nợ phải thu',
  'receptionist':'Nhân viên lễ tân','seo specialist':'Chuyên viên tối ưu công cụ tìm kiếm','sales admin':'Chuyên viên hỗ trợ kinh doanh',
  'system admin':'Quản trị viên hệ thống','talent acquisition':'Chuyên viên tuyển dụng','tax accountant':'Kế toán thuế',
  'telesales':'Chuyên viên tư vấn bán hàng qua điện thoại','uiux designer':'Chuyên viên thiết kế giao diện và trải nghiệm người dùng',
  'video editor':'Chuyên viên biên tập video','warehouse supervisor':'Giám sát kho',
};
export const stripPositionLevel=(value?:string)=>(value||'').replace(/^(Entry|Junior|Mid|Senior|Manager|Director)_/,'');
const levelLabels:Record<string,string>={Entry:'Mới bắt đầu',Junior:'Nhân viên',Mid:'Chuyên viên',Senior:'Chuyên viên cao cấp',Manager:'Quản lý',Director:'Giám đốc'};
export const levelName=(value?:string)=>levelLabels[value||'']||value||'Chưa xác định';
export function positionName(value?:string){
  if(!value)return '—';
  const cleaned=stripPositionLevel(value).replaceAll('_',' ').replace(/\s+/g,' ').trim();
  const vietnameseInParentheses=cleaned.match(/\(([^)]*[À-ỹ][^)]*)\)/i)?.[1];
  if(vietnameseInParentheses)return vietnameseInParentheses.replaceAll('&','và').trim();
  const withoutParentheses=cleaned.replace(/\s*\([^)]*\)\s*/g,' ').trim();
  const key=withoutParentheses.toLowerCase().replace(/[/-]/g,' ').replace(/\s+/g,' ').trim();
  return positionTranslations[key]||positionTranslations[cleaned.toLowerCase()]||cleaned;
}
export function uniquePositions<T extends {id:string}>(jobs:T[]):T[]{
  const result=new Map<string,T>();
  for(const job of jobs){const key=stripPositionLevel(job.id);const current=result.get(key);if(!current||job.id.startsWith('Junior_'))result.set(key,job)}
  return [...result.values()];
}
export const cn = (...values: Array<string|false|null|undefined>) => values.filter(Boolean).join(' ');
