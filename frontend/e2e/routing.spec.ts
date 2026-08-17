import { expect, test } from '@playwright/test';
test('các entry React tải đúng giao diện tiếng Việt',async({page})=>{
  await page.route('**/jobs',route=>route.fulfill({json:{jobs:[],categories:[]}}));
  await page.goto('/candidate.html');
  await expect(page.getByText('Vị trí đang tuyển')).toBeVisible();
});
test('link phỏng vấn hết hạn hiển thị lỗi rõ ràng',async({page})=>{
  await page.route('**/api/v1/slot/**/validate',route=>route.fulfill({status:403,json:{detail:{message:'Khung giờ phỏng vấn đã kết thúc.'}}}));
  await page.goto('/interview.html?slot=SLOT-EXPIRED');
  await expect(page.getByText('Chưa thể bắt đầu phỏng vấn')).toBeVisible();
  await expect(page.getByText('Khung giờ phỏng vấn đã kết thúc.')).toBeVisible();
});
