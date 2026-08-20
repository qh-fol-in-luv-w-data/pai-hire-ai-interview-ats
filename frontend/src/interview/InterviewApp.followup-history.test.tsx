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
  stop() {
    this.ondataavailable?.({ data: new Blob(['x'], { type: 'audio/webm' }) });
    this.onstop?.();
  }
}

describe('history gửi lên evaluate-step khi trả lời câu hỏi đào sâu', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('chèn đáp án của câu hỏi gốc vào history, không còn bỏ trống', async () => {
    stubIndexedDb();
    (document.documentElement as any).requestFullscreen = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder as any);

    const getUserMedia = vi.fn().mockResolvedValue({
      getAudioTracks: () => [{ stop: vi.fn() }],
      getTracks: () => [{ stop: vi.fn() }],
    });
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

    const evaluateCalls: { question_number: string; history: any[]; prep_id: string }[] = [];

    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.startsWith('/jobs')) return jsonResponse({ jobs: [{ id: 'Junior_Dev', title: 'Developer' }] });
      if (u.startsWith('/interview/prep')) {
        return jsonResponse({
          prep_id: 'prep1', follow_up_limit: 5,
          questions: { '1': { text: 'Câu hỏi gốc số 1', type: 'Technical' } },
        });
      }
      if (u.startsWith('/interview/evaluate-step')) {
        const fd = init!.body as FormData;
        const qn = String(fd.get('question_number'));
        const history = JSON.parse(String(fd.get('history')));
        evaluateCalls.push({ question_number: qn, history, prep_id: String(fd.get('prep_id')) });
        if (evaluateCalls.length === 1) {
          return jsonResponse({ need_pushback: true, pushback_text: 'Cụ thể hơn, con số ra sao?', pushback_audio: '/audio/pb.mp3', pushback_n: '1_1', transcript: 'Đây là câu trả lời gốc của tôi' });
        }
        return jsonResponse({ need_pushback: false, transcript: 'Đây là câu trả lời cho phần đào sâu' });
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

    // Trả lời câu hỏi gốc (01)
    await screen.findByText('Câu hỏi gốc số 1');
    fireEvent.click(screen.getByText('Bắt đầu trả lời'));
    fireEvent.click(await screen.findByText(/Dừng ghi/));
    await waitFor(() => expect(evaluateCalls.length).toBe(1));
    expect(evaluateCalls[0].question_number).toBe('1');
    // Lượt đầu tiên: chưa có lượt nào trước đó, history chỉ gồm câu hỏi gốc
    expect(evaluateCalls[0].history).toEqual([{ role: 'assistant', content: 'Câu hỏi gốc số 1' }]);

    // Câu hỏi đào sâu đã được chèn vào danh sách, bấm "Câu tiếp theo" để sang nó
    fireEvent.click(screen.getByText('Câu tiếp theo'));
    await screen.findByText('Cụ thể hơn, con số ra sao?');
    fireEvent.click(screen.getByText('Bắt đầu trả lời'));
    fireEvent.click(await screen.findByText(/Dừng ghi/));
    await waitFor(() => expect(evaluateCalls.length).toBe(2));
    expect(evaluateCalls[1].question_number).toBe('1');

    // Đây là điểm B1: history của lượt 2 PHẢI chứa đáp án của câu hỏi gốc
    expect(evaluateCalls[1].history).toEqual([
      { role: 'assistant', content: 'Câu hỏi gốc số 1' },
      { role: 'user', content: 'Đây là câu trả lời gốc của tôi' },
    ]);

    // B2: prep_id phải được gửi lên để server tự canh giới hạn đào sâu server-side
    expect(evaluateCalls[0].prep_id).toBe('prep1');
    expect(evaluateCalls[1].prep_id).toBe('prep1');

    // Câu đào sâu (id do SERVER cấp qua pushback_n, không phải client tự đếm) phải xuất hiện đúng vị trí
    await waitFor(() => expect(screen.getByText('Câu 2 / 2')).toBeInTheDocument());
  });
});
