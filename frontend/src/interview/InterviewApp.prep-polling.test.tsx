import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InterviewApp } from './InterviewApp';

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } }));
}

function stubIndexedDb() {
  const store = new Map<string, unknown>();
  const fakeRequest = () => { const req: any = {}; queueMicrotask(() => req.onsuccess?.()); return req; };
  const fakeDb: any = {
    objectStoreNames: { contains: () => true },
    transaction: () => ({
      objectStore: () => ({
        put: (value: unknown, key: string) => { store.set(key, value); return fakeRequest(); },
        get: (key: string) => { const req = fakeRequest(); (req as any).result = store.get(key); return req; },
        getAllKeys: () => { const req = fakeRequest(); (req as any).result = [...store.keys()]; return req; },
        delete: (key: string) => { store.delete(key); return fakeRequest(); },
      }),
    }),
  };
  vi.stubGlobal('indexedDB', { open: () => { const req: any = { result: fakeDb }; queueMicrotask(() => { req.onupgradeneeded?.(); req.onsuccess?.(); }); return req; } });
}

describe('sinh bộ đề chạy nền (A6) — candidate poll trạng thái thay vì chờ chặn', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });

  it('hiện "Đang chuẩn bị câu hỏi" trong lúc generating, tự chuyển sang câu hỏi khi status=ready', async () => {
    stubIndexedDb();
    (document.documentElement as any).requestFullscreen = vi.fn().mockResolvedValue(undefined);
    const getUserMedia = vi.fn().mockResolvedValue({
      getAudioTracks: () => [{ stop: vi.fn() }],
      getTracks: () => [{ stop: vi.fn() }],
    });
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

    let statusCallCount = 0;
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url);
      if (u.startsWith('/jobs')) return jsonResponse({ jobs: [{ id: 'Junior_Dev', title: 'Developer' }] });
      if (u.startsWith('/interview/prep/prepXYZ/status')) {
        statusCallCount += 1;
        if (statusCallCount < 3) return jsonResponse({ prep_id: 'prepXYZ', prep_status: 'generating' });
        return jsonResponse({ prep_id: 'prepXYZ', prep_status: 'ready', follow_up_limit: 2, questions: { '1': { text: 'Câu hỏi đã sinh xong', type: 'General' } } });
      }
      if (u.startsWith('/interview/prep')) {
        return jsonResponse({ prep_id: 'prepXYZ', prep_status: 'generating' });
      }
      return jsonResponse({});
    }));

    render(<InterviewApp />);
    await screen.findByText('Bắt đầu phỏng vấn');
    fireEvent.click(screen.getByText('Chọn vị trí'));
    fireEvent.click(screen.getByText('Developer'));
    const fileInput = document.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['cv'], 'cv.pdf', { type: 'application/pdf' })] } });
    fireEvent.click(screen.getByText('Tiếp tục'));
    await screen.findByText('Chuẩn bị trước khi bắt đầu');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Cho phép và bắt đầu'));

    // Trong lúc đang generating: màn hình "Đang chuẩn bị câu hỏi" phải hiện ra,
    // ứng viên KHÔNG bị treo trên request ban đầu.
    await screen.findByText('Đang chuẩn bị câu hỏi');

    // Sau khi poll đủ số lần và status chuyển ready, câu hỏi phải tự hiện ra.
    await waitFor(() => expect(screen.getByText('Câu hỏi đã sinh xong')).toBeInTheDocument(), { timeout: 15000 });
    expect(statusCallCount).toBeGreaterThanOrEqual(3);
  }, 20000);

  it('hiện lỗi và KHÔNG treo mãi khi prep_status trả về error', async () => {
    stubIndexedDb();
    (document.documentElement as any).requestFullscreen = vi.fn().mockResolvedValue(undefined);
    const getUserMedia = vi.fn().mockResolvedValue({
      getAudioTracks: () => [{ stop: vi.fn() }],
      getTracks: () => [{ stop: vi.fn() }],
    });
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url);
      if (u.startsWith('/jobs')) return jsonResponse({ jobs: [{ id: 'Junior_Dev', title: 'Developer' }] });
      if (u.startsWith('/interview/prep/prepERR/status')) {
        return jsonResponse({ prep_id: 'prepERR', prep_status: 'error', prep_error: 'Lỗi mô phỏng: hết hạn mức OpenAI' });
      }
      if (u.startsWith('/interview/prep')) {
        return jsonResponse({ prep_id: 'prepERR', prep_status: 'generating' });
      }
      return jsonResponse({});
    }));

    render(<InterviewApp />);
    await screen.findByText('Bắt đầu phỏng vấn');
    fireEvent.click(screen.getByText('Chọn vị trí'));
    fireEvent.click(screen.getByText('Developer'));
    const fileInput = document.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['cv'], 'cv.pdf', { type: 'application/pdf' })] } });
    fireEvent.click(screen.getByText('Tiếp tục'));
    await screen.findByText('Chuẩn bị trước khi bắt đầu');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Cho phép và bắt đầu'));

    await waitFor(() => expect(screen.getByText('Lỗi mô phỏng: hết hạn mức OpenAI')).toBeInTheDocument(), { timeout: 10000 });
  }, 15000);
});
