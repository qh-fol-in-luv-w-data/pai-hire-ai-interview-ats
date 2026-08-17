import type { ApiErrorShape } from './types';

export class ApiError extends Error { constructor(message: string, public status: number, public payload?: unknown) { super(message); } }

function detailMessage(payload: ApiErrorShape | undefined, fallback: string) {
  if (!payload) return fallback;
  if (typeof payload.detail === 'string') return payload.detail;
  if (payload.detail && typeof payload.detail === 'object' && payload.detail.message) return payload.detail.message;
  return payload.msg || payload.message || fallback;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(detailMessage(typeof payload === 'object' ? payload : undefined, `Yêu cầu thất bại (${response.status})`), response.status, payload);
  return payload as T;
}

export function adminApi<T>(path: string, init: RequestInit = {}) {
  const key = localStorage.getItem('pai_admin_key') || sessionStorage.getItem('pai_admin_key') || '';
  return api<T>(path, { ...init, headers: { 'X-Admin-Key': key, ...(init.headers || {}) } });
}

export const jsonInit = (method: string, body?: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
