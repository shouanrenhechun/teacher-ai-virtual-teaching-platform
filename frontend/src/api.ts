export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
export const SESSION_STORAGE_KEY = 'teaching-session-id';
const IDENTITY_KEY = 'teaching-practice-token';

export function practiceToken() {
  let token = localStorage.getItem(IDENTITY_KEY);
  if (!token || !/^[a-f0-9]{64}$/.test(token)) {
    token = Array.from(crypto.getRandomValues(new Uint8Array(32)), v => v.toString(16).padStart(2, '0')).join('');
    localStorage.setItem(IDENTITY_KEY, token);
  }
  return token;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('X-Practice-Token', practiceToken());
  let response: Response;
  try { response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers }); }
  catch { throw new Error('网络连接失败，请确认后端正在运行。输入内容已保留。'); }
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(typeof payload?.detail === 'string' ? payload.detail : `请求失败（HTTP ${response.status}）`, response.status);
  return payload as T;
}

export const jsonHeaders = () => ({ 'Content-Type': 'application/json' });
export const formatPercent = (value: number) => `${Math.round(value * 100)}%`;
export const formatScore = (value: number | null | undefined) => value == null ? '未评估' : value.toFixed(1);
export function formatDate(value: string) {
  const withZone = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(withZone));
}
