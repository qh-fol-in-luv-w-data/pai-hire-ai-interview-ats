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

class FakeMediaRecorder {
  static isTypeSupported() { return true; }
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  mimeType = 'audio/webm';
  constructor(_stream: unknown, _opts: unknown) {}
  start() {}
  stop() { this.ondataavailable?.({ data: new Blob(['x'], { type: 'audio/webm' }) }); this.onstop?.(); }
}

describe('STT thất bại (B6) — không được âm thầm coi là đã hoàn thành', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('hiện cảnh báo + nút thử lại khi transcript rỗng, chặn nộp bài, thử lại thành công thì mở khoá', async () => {
    stubIndexedDb();
    (document.documentElement as any).requestFullscreen = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder as any);
    const getUserMedia = vi.fn().mockResolvedValue({
      getAudioTracks: () => [{ stop: vi.fn() }],
      getTracks: () => [{ stop: vi.fn() }],
    });
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

    let evalCallCount = 0;
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url);
      if (u.startsWith('/jobs')) return jsonResponse({ jobs: [{ id: 'Junior_Dev', title: 'Developer' }] });
      if (u.startsWith('/interview/prep')) {
        return jsonResponse({ prep_id: 'prep1', follow_up_limit: 0, questions: { '1': { text: 'Câu hỏi duy nhất', type: 'General' } } });
      }
      if (u.startsWith('/interview/evaluate-step')) {
        evalCallCount += 1;
        // Lượt đầu: STT lỗi (transcript rỗng). Lượt sau (thử lại): thành công.
        if (evalCallCount === 1) return jsonResponse({ need_pushback: false, transcript: '' });
        return jsonResponse({ need_pushback: false, transcript: 'Đây là câu trả lời sau khi thử lại' });
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

    await screen.findByText('Câu hỏi duy nhất');
    fireEvent.click(screen.getByText('Bắt đầu trả lời'));
    fireEvent.click(await screen.findByText(/Dừng ghi/));

    // STT thất bại: cảnh báo phải hiện, nút Nộp bài phải bị khoá
    await screen.findByText(/Không nhận diện được giọng nói/);
    const submitBtn = await screen.findByText('Nộp bài phỏng vấn');
    expect(submitBtn.closest('button')).toBeDisabled();

    // Bấm "Thử lại"
    fireEvent.click(screen.getByText('Thử lại'));
    await waitFor(() => expect(screen.getByText('Đây là câu trả lời sau khi thử lại')).toBeInTheDocument());

    // Sau khi thử lại thành công: cảnh báo biến mất, nút Nộp bài mở khoá
    expect(screen.queryByText(/Không nhận diện được giọng nói/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Nộp bài phỏng vấn').closest('button')).not.toBeDisabled());
  });
});
