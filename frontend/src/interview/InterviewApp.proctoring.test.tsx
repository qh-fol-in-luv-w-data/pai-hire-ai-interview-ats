import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { InterviewApp } from './InterviewApp';

function stubIndexedDb() {
  const store = new Map<string, unknown>();
  const fakeRequest = () => {
    const req: any = {};
    queueMicrotask(() => req.onsuccess?.());
    return req;
  };
  const fakeDb: any = {
    objectStoreNames: { contains: () => true },
    transaction: () => ({
      objectStore: () => ({
        put: (value: unknown, key: string) => { store.set(key, value); return fakeRequest(); },
        get: (key: string) => { const req = fakeRequest(); (req as any).result = store.get(key); return req; },
        getAllKeys: () => { const req = fakeRequest(); (req as any).result = [...store.keys()]; return req; },
        delete: (key: string) => { store.delete(key); return fakeRequest(); },
      }),
      oncomplete: null as (() => void) | null,
      get complete() { return true; },
    }),
  };
  vi.stubGlobal('indexedDB', {
    open: () => {
      const req: any = { result: fakeDb };
      queueMicrotask(() => { req.onupgradeneeded?.(); req.onsuccess?.(); });
      return req;
    },
  });
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } }));
}

async function bootToInterviewing() {
  stubIndexedDb();
  const requestFullscreen = vi.fn().mockResolvedValue(undefined);
  (document.documentElement as any).requestFullscreen = requestFullscreen;

  const getUserMedia = vi.fn().mockResolvedValue({
    getAudioTracks: () => [{ stop: vi.fn() }],
    getTracks: () => [{ stop: vi.fn() }],
  });
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url);
    if (u.startsWith('/jobs')) return jsonResponse({ jobs: [{ id: 'Junior_Dev', title: 'Developer' }] });
    if (u.startsWith('/interview/prep')) return jsonResponse({ prep_id: 'prep1', follow_up_limit: 0, questions: { '1': { text: 'Câu hỏi mẫu số 1', type: 'General' } } });
    return jsonResponse({});
  }));

  render(<InterviewApp />);

  await screen.findByText('Bắt đầu phỏng vấn');
  fireEvent.click(screen.getByText('Chọn vị trí'));
  fireEvent.click(screen.getByText('Developer'));
  const cvFile = new File(['cv'], 'cv.pdf', { type: 'application/pdf' });
  const fileInput = document.querySelector('input[type=file]') as HTMLInputElement;
  fireEvent.change(fileInput, { target: { files: [cvFile] } });
  fireEvent.click(screen.getByText('Tiếp tục'));

  await screen.findByText('Chuẩn bị trước khi bắt đầu');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Cho phép và bắt đầu'));

  await screen.findByText('Câu hỏi mẫu số 1');
  return { requestFullscreen };
}

async function bootToInterviewingWithRef() {
  stubIndexedDb();
  window.history.replaceState(null, '', '/interview.html?slot=SLOT123');
  (document.documentElement as any).requestFullscreen = vi.fn().mockResolvedValue(undefined);
  const getUserMedia = vi.fn().mockResolvedValue({
    getAudioTracks: () => [{ stop: vi.fn() }],
    getTracks: () => [{ stop: vi.fn() }],
  });
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url);
    if (u.includes('/slot/SLOT123/validate')) return jsonResponse({ valid: true, app_id: 'APP1', position_id: 'Junior_Dev', level: 'Junior', interview_session: 'sess1' });
    if (u.includes('/applications/APP1/basic')) return jsonResponse({ name: 'Ứng viên Test', email: 't@x.com', job_id: 'Junior_Dev', level: 'Junior', job_title: 'Developer' });
    if (u.includes('/proctoring/session')) return jsonResponse({ embed_url: '/embed/cam', alerts_token: 'tok1', latest_alert_id: 0 });
    if (u.startsWith('/interview/prep')) return jsonResponse({ prep_id: 'prep1', follow_up_limit: 0, questions: { '1': { text: 'Câu hỏi mẫu số 1', type: 'General' } } });
    if (u.includes('/proctoring/alerts')) return jsonResponse({ alerts: [] });
    return jsonResponse({});
  }));

  render(<InterviewApp />);
  await screen.findByText('Chuẩn bị trước khi bắt đầu');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Cho phép và bắt đầu'));
  await screen.findByText('Câu hỏi mẫu số 1');
}

describe('cảnh báo AI từ camera giám sát', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); document.body.classList.remove('select-none'); });

  it('hiện popup khi iframe AI gửi postMessage proctoring_alert (vd: phát hiện điện thoại)', async () => {
    await bootToInterviewing();
    act(() => {
      window.dispatchEvent(new MessageEvent('message', { data: { type: 'proctoring_alert', alert_type: 'PHONE_DETECTED' } }));
    });
    await waitFor(() => expect(screen.getByText('Cảnh báo: Phát hiện điện thoại!')).toBeInTheDocument());
  });

  it('hiện popup khi nhận alert AI qua polling backend (vd: mất khuôn mặt)', async () => {
    await bootToInterviewingWithRef();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((url: any) => {
      const u = String(url);
      if (u.includes('/proctoring/alerts')) return jsonResponse({ alerts: [{ id: 1, alert_type: 'NO_FACE' }] });
      return jsonResponse({});
    });
    await waitFor(() => expect(screen.getByText('Cảnh báo: Mất khuôn mặt!')).toBeInTheDocument(), { timeout: 6000 });
  });
});

describe('giám sát chống gian lận trong lúc phỏng vấn', () => {
  beforeEach(() => { vi.useRealTimers(); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); delete (document.documentElement as any).requestFullscreen; document.body.classList.remove('select-none'); });

  it('tự động yêu cầu toàn màn hình khi bắt đầu phỏng vấn', async () => {
    const { requestFullscreen } = await bootToInterviewing();
    expect(requestFullscreen).toHaveBeenCalled();
  });

  it('hiện cảnh báo và đếm khi thoát toàn màn hình (gộp chung với chuyển tab/mất focus)', async () => {
    await bootToInterviewing();
    const combinedLabel = /Rời khỏi phỏng vấn/;
    expect(screen.getByText(combinedLabel).nextSibling).toHaveTextContent('0 lần');
    Object.defineProperty(document, 'fullscreenElement', { value: null, configurable: true });
    act(() => { document.dispatchEvent(new Event('fullscreenchange')); });
    await waitFor(() => expect(screen.getByText(/Bạn đã thoát chế độ toàn màn hình/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(combinedLabel).nextSibling).toHaveTextContent('1 lần'));
  });

  it('hiện cảnh báo khi chuyển tab (ẩn trang)', async () => {
    await bootToInterviewing();
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    act(() => { document.dispatchEvent(new Event('visibilitychange')); });
    await waitFor(() => expect(screen.getByText(/Bạn vừa rời khỏi tab phỏng vấn/i)).toBeInTheDocument());
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  it('hiện cảnh báo khi cửa sổ mất focus dù tab vẫn hiển thị (đa màn hình)', async () => {
    await bootToInterviewing();
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    act(() => { window.dispatchEvent(new Event('blur')); });
    await waitFor(() => expect(screen.getByText(/Cửa sổ phỏng vấn mất focus/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Rời khỏi phỏng vấn/).nextSibling?.textContent).not.toBe('0 lần'));
  });

  it('chặn phím tắt chụp màn hình / devtools và ghi nhận cảnh báo', async () => {
    await bootToInterviewing();
    const evt = new KeyboardEvent('keydown', { key: 'F12', bubbles: true, cancelable: true });
    act(() => { document.dispatchEvent(evt); });
    expect(evt.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.getByText(/chụp màn hình\/quay phim bị vô hiệu hoá/i)).toBeInTheDocument());
  });

  it('chặn menu chuột phải (contextmenu)', async () => {
    await bootToInterviewing();
    const evt = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    act(() => { document.dispatchEvent(evt); });
    expect(evt.defaultPrevented).toBe(true);
  });
});
