import { showToast } from './toast';
import { resolveApiBaseUrl } from './tauriBridge';

let cachedBaseUrl: string | null = null;

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

function extractErrorMessage(body: unknown, status: number): string {
  if (typeof body === 'string' && body.trim()) return body;
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if (typeof obj.detail === 'string') return obj.detail;
    if (obj.detail && typeof obj.detail === 'object') {
      const d = obj.detail as Record<string, unknown>;
      if (typeof d.error === 'string') return d.error;
      if (typeof d.message === 'string') return d.message;
    }
    if (typeof obj.error === 'string') return obj.error;
    if (typeof obj.message === 'string') return obj.message;
  }
  return `请求失败 (HTTP ${status})`;
}

export async function getApiBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl;
  try {
    cachedBaseUrl = await resolveApiBaseUrl();
  } catch (err) {
    const msg = err instanceof Error ? err.message : '未获取到 API 地址';
    throw new ApiError(msg, 0);
  }
  return cachedBaseUrl;
}

export function resetApiBaseUrlCache(): void {
  cachedBaseUrl = null;
}

export async function buildWsUrl(path: string): Promise<string> {
  const base = await getApiBaseUrl();
  const u = new URL(base);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  u.pathname = path.startsWith('/') ? path : `/${path}`;
  u.search = '';
  return u.toString();
}

export async function apiFetch<T = unknown>(
  path: string,
  init?: RequestInit & { silent?: boolean; skipToast?: boolean },
): Promise<T> {
  const base = await getApiBaseUrl();
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`;
  const { silent, skipToast, ...fetchInit } = init ?? {};
  let res: Response;
  try {
    res = await fetch(url, fetchInit);
  } catch (err) {
    const msg = err instanceof Error ? err.message : '网络请求失败';
    if (!silent && !skipToast) showToast(msg, 'error');
    throw new ApiError(msg, 0);
  }

  const contentType = res.headers.get('content-type') ?? '';
  let body: unknown = null;
  if (contentType.includes('application/json')) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  } else if (!res.ok) {
    try {
      body = await res.text();
    } catch {
      body = null;
    }
  }

  if (!res.ok) {
    const msg = extractErrorMessage(body, res.status);
    if (!silent && !skipToast) showToast(msg, 'error');
    throw new ApiError(msg, res.status, body);
  }

  return (body ?? ({} as T)) as T;
}

export async function apiGet<T = unknown>(path: string, silent?: boolean): Promise<T> {
  return apiFetch<T>(path, { method: 'GET', silent });
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  silent?: boolean,
): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: body != null ? { 'Content-Type': 'application/json' } : undefined,
    body: body != null ? JSON.stringify(body) : undefined,
    silent,
  });
}

export async function apiPatch<T = unknown>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: 'DELETE' });
}

export async function mediaUrl(relPath: string): Promise<string> {
  const base = await getApiBaseUrl();
  const q = new URLSearchParams({ path: relPath });
  return `${base}/api/media?${q.toString()}`;
}
